import sys; sys.path.insert(0,'/home/crobertson/labs/greek-fabric/scripts')
import junos
out = junos.cli('172.30.40.28', ['show configuration | display set | match "radsec|radius|dot1x|mac-radius|apply-groups|authentication-profile|access profile" | except "secret|key"'])
print(out)
