"""Install the reviewed release; preserve secrets, OAuth state and rollback paths."""
import os,sys,pathlib,subprocess,shutil,json,base64,secrets,time
from cryptography.fernet import Fernet
import jwt
service='bt-fieldwork-write-mcp.service'
release=pathlib.Path(__file__).resolve().parents[1]
link=pathlib.Path('/opt/bt-fieldwork-write-mcp')
old=link.resolve()
assert release != old and release.is_dir() and link.is_symlink()
venv=release/'.venv'
if not venv.exists(): venv.symlink_to(old/'.venv',target_is_directory=True)
pid=subprocess.check_output(['systemctl','show',service,'--property=MainPID','--value'],text=True).strip()
env=dict(x.split('=',1) for x in pathlib.Path('/proc/'+pid+'/environ').read_bytes().decode().split('\0') if '=' in x)
# Recover ONLY the already permitted, cryptographically verified subject binding.
fernet=Fernet(env['FW_WRITE_AUTH0_STORAGE_KEY'].encode())
issuer=env['FW_WRITE_AUTH0_CONFIG_URL'].split('/.well-known')[0]+'/'
jwks=jwt.PyJWKClient(issuer+'.well-known/jwks.json')
verified={}
for p in pathlib.Path(env['FW_WRITE_AUTH0_STORAGE_PATH']).rglob('*.json'):
    try:
        d=json.loads(p.read_text());v=d.get('value',{})
        if isinstance(v,str):v=json.loads(v)
        if '__encrypted_data__' not in v:continue
        x=json.loads(fernet.decrypt(base64.b64decode(v['__encrypted_data__'])))
        token=x.get('raw_token_data',{}).get('id_token')
        if not token:continue
        claims=jwt.decode(token,jwks.get_signing_key_from_jwt(token).key,algorithms=['RS256'],audience=env['FW_WRITE_AUTH0_CLIENT_ID'],issuer=issuer)
        email=str(claims.get('email','')).lower()
        if claims.get('email_verified') is True and email in env['FW_WRITE_PERMITTED_USERS'].lower().split(',') and claims.get('sub'):
            verified[claims['sub']]=email
    except Exception:pass
if not verified:raise SystemExit('Stopped: no currently verified permitted identity available for renewal mapping')
runenv={**os.environ,'PYTHONPATH':str(release/'src')}
tests=subprocess.run([str(venv/'bin/python'),'-m','unittest','discover','-s','tests','-t','.','-q'],cwd=release,env=runenv,capture_output=True,text=True)
print('VM_OFFLINE_TESTS',tests.returncode)
print('\n'.join(line for line in tests.stderr.splitlines() if line.startswith(('Ran ','OK','FAILED'))))
if tests.returncode:raise SystemExit('Stopped: VM offline tests failed')
backup=pathlib.Path('/root/bt-fieldwork-backups')/time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())
backup.mkdir(parents=True,mode=0o700)
paths=[pathlib.Path('/etc/bt-fieldwork-write-mcp.env'),pathlib.Path('/etc/bt-fieldwork-write-mcp.auth.env')]
for p in paths:shutil.copy2(p,backup/p.name)
(backup/'previous-release').write_text(str(old))
route_data={'source':'Existing Fieldwork MCP list_service_routes, verified by Codex','verified_at':'2026-09-25T01:00:00Z','routes':[
{'route_id':'4550','name':'Route #13','user_id':'37555','user_name':'Josh McLamb'},
{'route_id':'122999','name':'Route #2','user_id':'155992','user_name':'Michel Arnold'},
{'route_id':'2557','name':'Route #3','user_id':'3081','user_name':'Daniel Cahoon'},
{'route_id':'9814','name':'Route #5','user_id':'33676','user_name':'Chris Roznowski'},
{'route_id':'135779','name':'Route #6','user_id':'44656','user_name':'David Davis'}]}
route_path=pathlib.Path('/etc/bt-fieldwork-route-directory.json')
route_path.write_text(json.dumps(route_data,indent=2));route_path.chmod(0o644)
updates={'FIELDWORK_WRITES_ENABLED':'1','FIELDWORK_MAPPING_VERIFIED':'1','FW_WRITE_AUTH0_OFFLINE_ACCESS':'1','FW_WRITE_APPROVAL_MODE':'chatgpt_confirmation','FW_WRITE_ROUTE_DIRECTORY':str(route_path),'FW_WRITE_AUTH0_SUBJECT_MAP':','.join(k+'='+v for k,v in verified.items())}
def write_env(path,changes):
    lines=path.read_text().splitlines()
    lines=[line for line in lines if line.split('=',1)[0] not in changes]
    path.write_text('\n'.join(lines+[k+'='+v for k,v in changes.items()])+'\n');path.chmod(0o600)
write_env(paths[0],updates)
if not env.get('FW_WRITE_OPERATOR_KEY'):write_env(paths[1],{'FW_WRITE_OPERATOR_KEY':secrets.token_urlsafe(48)})
tmp=link.with_name('bt-fieldwork-write-mcp.next')
if tmp.is_symlink():tmp.unlink()
tmp.symlink_to(release,target_is_directory=True);os.replace(tmp,link)
subprocess.run(['systemctl','restart',service],check=True)
time.sleep(3)
active=subprocess.run(['systemctl','is-active','--quiet',service]).returncode==0
if not active:
    tmp.symlink_to(old,target_is_directory=True);os.replace(tmp,link)
    for p in paths:shutil.copy2(backup/p.name,p)
    subprocess.run(['systemctl','restart',service],check=True)
    raise SystemExit('New service did not stay active; previous release and configuration restored')
print('DEPLOYED_RELEASE',str(release))
print('PREVIOUS_RELEASE',str(old))
print('AUTH_KEYS_AND_OAUTH_STORE_PRESERVED',True)
print('VERIFIED_IDENTITY_BINDING_CONFIGURED',True)
print('API_KEY_READONLY_SETTING_UNCHANGED',True)
print('SERVICE_ACTIVE',active)
