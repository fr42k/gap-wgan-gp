import os
runori = 'python wgan_gp_pytorch.py'
rungap = 'python wgan_gp.py'
cps = '"c:\\Program Files\\7-Zip\\7z" a -tzip results.zip tmp'
sd = 'python sendmail.py'

os.system(runori)
os.system(rungap)
os.system(cps)
os.system(sd)