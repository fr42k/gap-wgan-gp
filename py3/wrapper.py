import os
runori = 'python wgan_gp_pytorch.py'
rungap = 'python wgan_gp.py'
cpsgap = '"c:\\Program Files\\7-Zip\\7z" a -tzip resultsg.zip tmp\\cifar10\\GAP'
cpsori = '"c:\\Program Files\\7-Zip\\7z" a -tzip resultso.zip tmp\\cifar10\\origin'
sdori = 'python sendmail_ori.py'
sdgap = 'python sendmail_gap.py'

os.system(runori)
os.system(cpsori)
os.system(sdori)
os.system(rungap)
os.system(cpsgap)
os.system(sdgap)