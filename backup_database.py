"""Manual local pilot backup. Must be protected like confidential customer data."""
from pathlib import Path
import sqlite3,datetime,hashlib,json
ROOT=Path(__file__).parent
source=ROOT/'smartquote_local.db'
if not source.exists():raise SystemExit('Nothing to back up yet. Create a quote first.')
folder=ROOT/'backups';folder.mkdir(exist_ok=True)
filename=folder/('smartquote_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'.db')
with sqlite3.connect(source) as c,sqlite3.connect(filename) as b:c.backup(b)
with sqlite3.connect(filename) as c:
 result=c.execute('PRAGMA integrity_check').fetchone()[0]
 if result!='ok':raise RuntimeError('Database integrity failed: '+result)
digest=hashlib.sha256(filename.read_bytes()).hexdigest()
(folder/(filename.stem+'.sha256')).write_text(digest+'  '+filename.name+'\n',encoding='utf-8')
print('Backup saved:',filename)
print('SHA-256:',digest)
print('Copy both backup files to a protected, separate location.')
