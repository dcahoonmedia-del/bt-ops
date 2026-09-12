import unittest

from bt_intake_proof.desk_origin import authenticate_control_origin, parse_ar_method_results

EVIDENCE = {"fetched_via": "contactus_gmail_api", "gmail_message_id": "synthetic-review-only"}


def _auth(headers, sender="daniel@btpestcontrol.com", evidence=None):
    return authenticate_control_origin(headers, sender, evidence or EVIDENCE)


class DeskOriginParseTests(unittest.TestCase):
    def test_codex_mixed_dkim_does_not_authorize(self) -> None:
        result = _auth(
            [
                (
                    "Authentication-Results",
                    "mx.google.com; dkim=fail header.i=@btpestcontrol.com; "
                    "dkim=pass header.i=@attacker.test; "
                    "spf=fail smtp.mailfrom=attacker@attacker.test",
                )
            ]
        )
        self.assertFalse(result["accepted"])
        self.assertFalse(result["dkim_ok"])
        self.assertFalse(result["full_identity_pass"])
        self.assertEqual(result["reason"], "provider_auth_failed")

    def test_reversed_multiple_dkim_and_spf(self) -> None:
        mixed = _auth(
            [
                (
                    "Authentication-Results",
                    "mx.google.com; dkim=pass header.i=@attacker.test; "
                    "dkim=fail header.i=@btpestcontrol.com; "
                    "spf=pass smtp.mailfrom=attacker@attacker.test; "
                    "spf=fail smtp.mailfrom=daniel@btpestcontrol.com",
                )
            ]
        )
        self.assertFalse(mixed["accepted"])
        mailbox = _auth(
            [
                (
                    "Authentication-Results",
                    "mx.google.com; dkim=fail header.i=@attacker.test; "
                    "dkim=pass header.i=daniel@btpestcontrol.com; "
                    "spf=fail smtp.mailfrom=attacker@attacker.test; "
                    "spf=pass smtp.mailfrom=daniel@btpestcontrol.com",
                )
            ]
        )
        self.assertTrue(mailbox["accepted"])
        self.assertEqual(mailbox["identity_level"], "mailbox_bound_provider_result")
        self.assertFalse(mailbox["full_identity_pass"])

    def test_domain_dkim_is_not_mailbox_identity(self) -> None:
        result = _auth(
            [
                (
                    "Authentication-Results",
                    "mx.google.com; dkim=pass header.i=@btpestcontrol.com; "
                    "spf=fail smtp.mailfrom=contactus@btpestcontrol.com",
                )
            ]
        )
        self.assertFalse(result["accepted"])
        self.assertTrue(result["dkim_domain_ok"])
        self.assertFalse(result["dkim_mailbox_ok"])
        self.assertEqual(result["reason"], "domain_dkim_not_mailbox_identity")
        self.assertFalse(result["trusted_domain_dkim_as_mailbox"])

    def test_mailbox_spf_alone_authorizes(self) -> None:
        result = _auth(
            [
                (
                    "Authentication-Results",
                    "mx.google.com; dkim=permerror header.i=@btpestcontrol.com; "
                    "spf=pass smtp.mailfrom=daniel@btpestcontrol.com",
                )
            ]
        )
        self.assertTrue(result["accepted"])
        self.assertTrue(result["spf_mailbox_ok"])
        self.assertFalse(result["full_identity_pass"])

    def test_lookalike_domains_fail(self) -> None:
        cases = [
            "mx.google.com; dkim=pass header.i=@btpestcontrol.com.evil; spf=pass smtp.mailfrom=daniel@btpestcontrol.com.evil",
            "mx.google.com; dkim=pass header.i=@btpestcontrol.com.attacker.test; spf=pass smtp.mailfrom=attacker@btpestcontrol.com.attacker.test",
            "mx.google.com; dkim=pass header.i=daniel@btpestcontro1.com; spf=pass smtp.mailfrom=daniel@btpestcontro1.com",
        ]
        for ar in cases:
            with self.subTest(ar=ar):
                result = _auth([("Authentication-Results", ar)])
                self.assertFalse(result["accepted"], result)

    def test_lookalike_authserv_fails(self) -> None:
        result = _auth(
            [
                (
                    "Authentication-Results",
                    "mx.google.com.evil; dkim=pass header.i=daniel@btpestcontrol.com; "
                    "spf=pass smtp.mailfrom=daniel@btpestcontrol.com",
                )
            ]
        )
        self.assertFalse(result["accepted"])
        self.assertEqual(result["reason"], "authentication_results_not_gmail")

    def test_duplicate_headers_use_only_the_first(self) -> None:
        result = _auth(
            [
                (
                    "Authentication-Results",
                    "mx.google.com; dkim=fail header.i=daniel@btpestcontrol.com; "
                    "spf=fail smtp.mailfrom=daniel@btpestcontrol.com",
                ),
                (
                    "Authentication-Results",
                    "mx.google.com; dkim=pass header.i=daniel@btpestcontrol.com; "
                    "spf=pass smtp.mailfrom=daniel@btpestcontrol.com",
                ),
            ]
        )
        self.assertFalse(result["accepted"])
        self.assertEqual(result["reason"], "provider_auth_failed")

    def test_malformed_headers_fail_closed(self) -> None:
        self.assertFalse(_auth([("Authentication-Results", "mx.google.com")]).get("accepted"))
        self.assertFalse(_auth([("Authentication-Results", "mx.google.com; ;;; dkim=pass")]).get("accepted"))
        self.assertFalse(_auth([("Authentication-Results", "mx.google.com; dkim=pass")]).get("accepted"))
        self.assertFalse(_auth([("ARC-Authentication-Results", "mx.google.com; dkim=pass header.i=daniel@btpestcontrol.com")]).get("accepted"))
        self.assertEqual(_auth([]).get("reason"), "authentication_results_missing")

    def test_method_properties_stay_bound(self) -> None:
        methods = parse_ar_method_results(
            "mx.google.com; dkim=fail header.i=@btpestcontrol.com; "
            "dkim=pass header.i=@attacker.test; "
            "spf=fail smtp.mailfrom=daniel@btpestcontrol.com"
        )
        dkim = [item for item in methods if item["method"] == "dkim"]
        self.assertEqual(dkim[0]["result"], "fail")
        self.assertEqual(dkim[0]["props"]["header.i"], "@btpestcontrol.com")
        self.assertEqual(dkim[1]["result"], "pass")
        self.assertEqual(dkim[1]["props"]["header.i"], "@attacker.test")
        spf = [item for item in methods if item["method"] == "spf"][0]
        self.assertEqual(spf["result"], "fail")
        self.assertEqual(spf["props"]["smtp.mailfrom"], "daniel@btpestcontrol.com")


if __name__ == "__main__":
    unittest.main()
