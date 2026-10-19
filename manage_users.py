"""Run: python manage_users.py bootstrap | add coordinator_name coordinator | add manager_name manager"""
import sys,getpass
import security

def main():
 mode=sys.argv[1] if len(sys.argv)>1 else 'bootstrap'
 if mode=='bootstrap' and security.count():
  print('User accounts already exist. Sign in to SmartQuote.');return
 if mode not in ('bootstrap','add'):raise SystemExit('Use bootstrap or add USERNAME ROLE')
 if mode=='bootstrap':username=input('Choose initial administrator username: ').strip();role='admin'
 else:
  if len(sys.argv)<4:raise SystemExit('Usage: python manage_users.py add USERNAME coordinator|manager|admin')
  username=sys.argv[2];role=sys.argv[3]
  if role=='admin' and not security.count():raise SystemExit('Bootstrap an administrator first')
 p1=getpass.getpass('Password (12+ characters): ');p2=getpass.getpass('Confirm password: ')
 if p1!=p2:raise SystemExit('Passwords do not match.')
 print('Account created:',security.add_user(username,p1,role),'role:',role)
if __name__=='__main__':main()
