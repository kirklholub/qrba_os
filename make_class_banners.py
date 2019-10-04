#!/usr/local/bin/python2
import sys
from pyfiglet import figlet_format

# https://stackoverflow.com/questions/9632995/how-to-easily-print-ascii-art-text


# cstr = "OrganizationExcludes, Quota, Cluster, Clusterpath, ADzone, Organization, Host, WinDC, DNSdomain, NfsExport, Report, Sysadmin, Restriction"
# cstr = "QuotaUsage"
# cstr = "POST_SAVE, IPzone"
cstr = "UserSession"

classes = cstr.split(', ')
allclasses = []
for c in classes:
    allclasses.append(c)
for c in classes:
    allclasses.append(c + "ModelTests")

for c in allclasses:
    # print( "c is " + str(c) )
    ff = figlet_format(c)
    ff = str(ff).split('\n')
    # print( "   len(ff) = " + str(len(ff)) )
    if len(ff) > 7:
        for i in range(0, 6):
            # print( "     ff[" + str(i) + "] = " + str(ff[i]) )
            ff[i] = ff[i] + ff[i + 6]
        ff = ff[0:6]

    hashline = ''
    for i in range(1, len(ff[0]) + 8):
        hashline = hashline + '#'
    print(hashline)

    for f in ff:
        if f != '':
            print("#   " + str(f) + "  #")
    print(hashline + "\n")
