import unittest
from bt_fieldwork_write_mcp.fieldwork import TypedFieldworkClient, FakeTransport, HttpTransport, _flatten
from bt_fieldwork_write_mcp.errors import GateError
from bt_fieldwork_write_mcp.secrets import InMemoryApiKey

class LiveContractTests(unittest.TestCase):
    def test_display_date_does_not_erase_live_schedule(self):
        t = FakeTransport()
        t.work_orders['1'] = {'id': 1, 'service_appointment_id': 2, 'starts_at_date':'09/25/2026', 'starts_at':'2026-09-25T12:00:00.000-04:00', 'customer_name':'Test customer', 'location_address':'Test address', 'service_route_ids':[2557]}
        result = TypedFieldworkClient(t).list_work_orders(start_date='2026-09-25',end_date='2026-09-25')
        self.assertEqual(len(result['items']),1)
        self.assertEqual(result['items'][0]['customer_name'],'Test customer')
        self.assertEqual(result['items'][0]['location_address'],'Test address')

    def test_read_ids_cannot_escape_typed_resource(self):
        t = FakeTransport(); c=TypedFieldworkClient(t)
        for value in ('../profile','1?x=2','1/../../profile','0','-1'):
            with self.assertRaises(GateError): c.get_customer(value)
            with self.assertRaises(GateError): c.get_work_order(value)
            with self.assertRaises(GateError): c.get_location('1',value)
        self.assertEqual(t.calls,[])

    def test_role_tracks_current_profile(self):
        t=FakeTransport();c=TypedFieldworkClient(t)
        self.assertEqual(c.get_api_role(),'readonly')
        t.api_role='writer'
        self.assertEqual(c.get_api_role(),'writer')

    def test_patch_matches_published_nested_contract(self):
        t=FakeTransport();c=TypedFieldworkClient(t)
        t.work_orders['10']={'id':10,'service_appointment_id':20,'instructions':'old','private_notes':'retained'}
        c.patch_work_order_fields({'work_order_id':10,'service_appointment_id':20}, {'instructions':'new'}, ['instructions'])
        call=t.calls[-1]
        self.assertEqual(call['path'],'/work_orders/20')
        self.assertEqual(_flatten(call['body']), [('service_appointment[appointment_occurrences_attributes][][id]','10'),('service_appointment[appointment_occurrences_attributes][][instructions]','new')])
        self.assertEqual(t.work_orders['10']['private_notes'],'retained')

    def test_unrecognized_upstream_shape_is_not_empty_success(self):
        class Broken(FakeTransport):
            def request(self,*args,**kwargs): return 200, {'unexpected':'shape'}
        with self.assertRaises(GateError): TypedFieldworkClient(Broken()).list_work_orders(start_date='2026-09-25',end_date='2026-09-25')

    def test_invalid_calendar_date_rejected(self):
        t=FakeTransport()
        with self.assertRaises(GateError): TypedFieldworkClient(t).list_work_orders(start_date='2026-02-31')
        self.assertEqual(t.calls,[])

class ChatGPTApprovalTests(unittest.TestCase):
    def setUp(self):
        from tests.test_write_mcp import Harness
        from dataclasses import replace
        self.h=Harness(api_role='writer')
        self.h.service.settings=replace(self.h.settings,approval_mode='chatgpt_confirmation')
    def tearDown(self): self.h.close()
    def test_exact_confirmed_proposal_executes_once(self):
        from tests.test_write_mcp import IDENTITY
        p=self.h.propose_notes('approved standing note')
        r=self.h.service.execute(p['proposal_id'],IDENTITY,approved=True,expected_digest=p['digest'])
        self.assertTrue(r['ok'],r)
        self.assertEqual(self.h.service.execute(p['proposal_id'],IDENTITY,approved=True,expected_digest=p['digest'])['gate'],'approval_replayed')
    def test_missing_confirmation_or_wrong_digest_does_not_write(self):
        from tests.test_write_mcp import IDENTITY
        p=self.h.propose_notes('approved standing note')
        for approved,digest in [(False,p['digest']),(True,'wrong')]:
            r=self.h.service.execute(p['proposal_id'],IDENTITY,approved=approved,expected_digest=digest)
            self.assertEqual(r['gate'],'operator_approval_required')
        self.assertFalse(any(c['method']=='PATCH' for c in self.h.transport.calls))
    def test_live_readonly_role_blocks_confirmed_proposal(self):
        from tests.test_write_mcp import IDENTITY
        p=self.h.propose_notes('approved standing note')
        self.h.transport.api_role='readonly'
        r=self.h.service.execute(p['proposal_id'],IDENTITY,approved=True,expected_digest=p['digest'])
        self.assertEqual(r['gate'],'readonly_api_role')
        self.assertFalse(any(c['method']=='PATCH' for c in self.h.transport.calls))
