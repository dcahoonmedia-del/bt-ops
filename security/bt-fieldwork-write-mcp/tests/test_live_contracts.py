import unittest
from bt_fieldwork_write_mcp.fieldwork import LIVE_PERMISSION_ROLES, TypedFieldworkClient, FakeTransport, HttpTransport, _flatten
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

    def test_exact_live_permission_roles_are_writer_without_a_literal_writer(self):
        t=FakeTransport(); t.api_role='writer'
        status, body = t.request('GET','/profile')
        self.assertEqual(status, 200)
        self.assertEqual(body['roles'], list(LIVE_PERMISSION_ROLES))
        self.assertNotIn('writer', body['roles'])
        self.assertEqual(TypedFieldworkClient(t).get_api_role(), 'writer')

    def test_readonly_wins_over_known_permissions(self):
        t=FakeTransport(); t.api_role='readonly'
        _status, body = t.request('GET','/profile')
        self.assertIn('readonly', body['roles'])
        self.assertTrue(set(LIVE_PERMISSION_ROLES).issubset(body['roles']))
        self.assertEqual(TypedFieldworkClient(t).get_api_role(), 'readonly')

    def test_unknown_empty_and_failed_profile_stay_unverified(self):
        unknown=FakeTransport(); unknown.api_role='unknown'
        with self.assertRaises(GateError) as caught:
            TypedFieldworkClient(unknown).get_api_role()
        self.assertEqual(caught.exception.gate, 'api_role_unverified')
        class Fixed(FakeTransport):
            def __init__(self, status, body):
                super().__init__(); self._status=status; self._body=body
            def request(self, method, path, body=None, query=None):
                if method=='GET' and path=='/profile':
                    self.calls.append({'method':method,'path':path})
                    return self._status, self._body
                return super().request(method, path, body, query)
        for status, body in ((200, {'roles': []}), (200, {'roles': 'schedule'}), (200, {}), (200, {'roles': [1]})):
            with self.assertRaises(GateError) as caught:
                TypedFieldworkClient(Fixed(status, body)).get_api_role()
            self.assertEqual(caught.exception.gate, 'api_role_unverified')
        failed=FakeTransport(); failed.api_role='fail'
        with self.assertRaises(GateError) as caught:
            TypedFieldworkClient(failed).get_api_role()
        self.assertEqual(caught.exception.gate, 'fieldwork_api_auth_unresolved')

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
        self.h=Harness(api_role='writer', writes_enabled=True, mapping_verified=True)
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
        before=len([c for c in self.h.transport.calls if c['path']=='/profile'])
        r=self.h.service.execute(p['proposal_id'],IDENTITY,approved=True,expected_digest=p['digest'])
        after=len([c for c in self.h.transport.calls if c['path']=='/profile'])
        self.assertEqual(after-before, 1)
        self.assertEqual(r['gate'],'readonly_api_role')
        self.assertEqual(r['gates']['api_role'], 'readonly')
        self.assertFalse(r['gates']['live_ready'])
        again=len([c for c in self.h.transport.calls if c['path']=='/profile'])
        self.assertEqual(self.h.service.gates()['api_role'], 'readonly')
        self.assertEqual(len([c for c in self.h.transport.calls if c['path']=='/profile']), again)
        self.assertFalse(any(c['method']=='PATCH' for c in self.h.transport.calls))

    def test_nonempty_operator_approval_does_not_skip_chatgpt_confirmation(self):
        from tests.test_write_mcp import IDENTITY
        p=self.h.propose_notes('approved standing note')
        junk=self.h.service.execute(p['proposal_id'], IDENTITY, operator_approval='not-a-token', approved=True, expected_digest=p['digest'])
        self.assertTrue(junk['ok'], junk)
        self.assertTrue(any(c['method']=='PATCH' for c in self.h.transport.calls))

    def test_junk_string_without_exact_digest_is_not_proof(self):
        from tests.test_write_mcp import IDENTITY
        p=self.h.propose_notes('approved standing note')
        self.h.transport.work_orders['10']={'id':10,'service_appointment_id':20,'customer_id':41,'service_location_id':77,'instructions':'old','private_notes':'secret','starts_at':'2026-09-25T08:00:00-04:00','duration':60,'service_route_ids':[2557]}
        other=self.h.service.propose('update_work_order_notes', {'work_order_id':'10','service_appointment_id':'20','instructions':'other'}, IDENTITY)
        self.assertTrue(other.get('ok'), other)
        for kwargs in (
            {'operator_approval':'please', 'approved':True, 'expected_digest':'tampered'},
            {'operator_approval':'please', 'approved':None, 'expected_digest':p['digest']},
            {'operator_approval':'please', 'approved':True, 'expected_digest':other['digest']},
        ):
            result=self.h.service.execute(p['proposal_id'], IDENTITY, **kwargs)
            self.assertEqual(result['gate'], 'operator_approval_required', result)
        self.assertFalse(any(c['method']=='PATCH' for c in self.h.transport.calls))

    def test_stored_digest_tamper_rejected(self):
        from tests.test_write_mcp import IDENTITY
        p=self.h.propose_notes('approved standing note')
        self.h.store._conn.execute("UPDATE proposals SET digest=? WHERE proposal_id=?", ('0'*64, p['proposal_id']))
        result=self.h.service.execute(p['proposal_id'], IDENTITY, approved=True, expected_digest=p['digest'])
        self.assertEqual(result['gate'], 'operator_approval_required')
        self.assertEqual(result['reason'], 'stored_proposal_digest_mismatch')
        self.assertFalse(any(c['method']=='PATCH' for c in self.h.transport.calls))

    def test_chatgpt_tool_has_no_operator_approval_parameter(self):
        import asyncio
        from bt_fieldwork_write_mcp.oauth_rs import JwtTokenVerifier
        from bt_fieldwork_write_mcp.server import build_mcp, request_identity
        from tests.test_write_mcp import IDENTITY
        server=build_mcp(self.h.service, self.h.service.settings, JwtTokenVerifier(self.h.service.settings))
        tool=next(item for item in server._tool_manager.list_tools() if item.name=='execute_approved_write')
        self.assertNotIn('operator_approval', tool.parameters['properties'])
        names={item.name for item in server._tool_manager.list_tools()}
        self.assertEqual(len(names), 13)
        proposed=self.h.propose_notes('wrapper note')
        import bt_fieldwork_write_mcp.server as server_mod
        server_mod.request_identity = lambda: dict(IDENTITY)
        try:
            result=asyncio.run(tool.fn(proposed['proposal_id'], approved=True, expected_digest=proposed['digest']))
        finally:
            server_mod.request_identity = request_identity
        self.assertTrue(result['ok'], result)
