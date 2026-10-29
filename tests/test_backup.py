# SPDX-License-Identifier: BUSL-1.1
# Copyright © 2026 Zyvor AI Labs Private Limited
import json, os, sqlite3, stat, tempfile, threading, unittest, urllib.error, urllib.request
from server.app import make_server
from server.core import Store, Problem

class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.now=1_800_000_000.; self.store=Store(self.temp.name+'/db',lambda:self.now); self.dir=self.temp.name+'/backups'
    def tearDown(self): self.store.db.close(); self.temp.cleanup()
    def test_snapshot_is_complete_private_and_checksummed(self):
        self.store.tenant('team',8); job=self.store.submit('team',dict(runtime='demo',memoryGiB=4)); self.store.create_join('x')
        r=self.store.backup(self.dir); path=os.path.join(self.dir,r['file'])
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode),0o600); self.assertEqual(stat.S_IMODE(os.stat(self.dir).st_mode),0o700)
        import hashlib; self.assertEqual(hashlib.sha256(open(path,'rb').read()).hexdigest(),r['sha256'])
        c=sqlite3.connect(path); self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        self.assertEqual(c.execute('SELECT id FROM jobs').fetchone()[0],job); self.assertEqual(c.execute('SELECT COUNT(*) FROM join_codes').fetchone()[0],1); c.close()
        self.assertEqual([f for f in os.listdir(self.dir) if f.endswith('.part')],[])
        restored=Store(path); self.assertEqual(restored.snapshot()['jobs'][0]['id'],job); restored.db.close()   # a snapshot opens as a working store
    def test_same_second_does_not_overwrite_and_retention_prunes_oldest(self):
        names=[]
        for i in range(5): names.append(self.store.backup(self.dir,keep=3)['file'])
        self.assertEqual(len(set(names)),5); left=sorted(os.listdir(self.dir)); self.assertEqual(len(left),3); self.assertEqual(left,sorted(names[-3:]))    # the three newest survive, including the '-N' same-second ones
    def test_only_backup_files_are_pruned(self):
        os.makedirs(self.dir); open(self.dir+'/notes.txt','w').write('keep me'); self.store.backup(self.dir,keep=1); self.store.backup(self.dir,keep=1)
        self.assertIn('notes.txt',os.listdir(self.dir)); self.assertEqual(len([f for f in os.listdir(self.dir) if f.startswith('gryvia-')]),1)
    def test_keep_validation(self):
        for bad in (0,101,True,'7',None):
            with self.assertRaises(Problem): self.store.backup(self.dir,keep=bad)
    def test_http_admin_only_and_no_client_path(self):
        self.store.db.close(); self.store=Store(self.temp.name+'/db2'); srv=make_server(self.store,{'a'*32:{'role':'admin'},'t'*32:{'role':'tenant','tenant':'default'}},port=0)
        srv.backup_dir=self.dir; th=threading.Thread(target=srv.serve_forever,daemon=True); th.start(); base='http://127.0.0.1:%d'%srv.server_port
        def post(token,body):
            r=urllib.request.Request(base+'/api/backup',headers={'Authorization':'Bearer '+token},data=json.dumps(body).encode())
            try:
                with urllib.request.urlopen(r) as res: return res.status,json.load(res)
            except urllib.error.HTTPError as e: return e.code,json.load(e)
        try:
            self.assertEqual(post('t'*32,{})[0],403)
            status,r=post('a'*32,{'path':'/tmp/evil','keep':2}); self.assertEqual(status,201)
            self.assertEqual(os.listdir(self.dir),[r['file']]); self.assertFalse(os.path.exists('/tmp/evil'))    # the body's `path` is ignored
            srv.backup_dir=None; self.assertEqual(post('a'*32,{})[0],409)
        finally: srv.shutdown(); srv.server_close(); th.join()
if __name__=='__main__': unittest.main()
