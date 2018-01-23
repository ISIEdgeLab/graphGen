#!/usr/bin/python

import sys, re

if len(sys.argv) <= 2:
    print "Usage %s <input file> <output file>\n"
    sys.exit(0)

in_fp = open(str(sys.argv[1]), 'r')
out_fp = open(str(sys.argv[2]), 'w')

max_if = 0
old_line = ""
for line in in_fp:
    tokens = line.split()
    if len(tokens) >= 1 and re.match('\$\{if[0-9]\}_loss', tokens[0]):
        m = re.search('[0-9]', tokens[0])
        if m:
            val = int(m.group(0))
            if val > max_if:
                max_if = val
    elif len(tokens) >= 1 and re.match('router1\[[0-9]\]', tokens[0]):
        old_line = line
        break

    out_fp.write(line)

out_fp.write("\n//Dec TTL\n\n")
for ifs in range(max_if):
    out_fp.write("ttl_%d :: DecIPTTL;\n" % (ifs + 1))
    out_fp.write("ttl_%d[1] -> ICMPError(${if%d}:ip, timeexceeded) -> router1;\n" % ((ifs + 1), (ifs + 1)))

out_fp.write("\n")

count = 1
tokens = old_line.split()
if len(tokens) >= 3 and re.match('router1\[[0-9]\]', tokens[0]):
    c = 0
    for token in tokens:
        if c == 2:
            out_fp.write(" ttl_%d ->" % count)
            count = count + 1
        out_fp.write(" %s" % token)
        c = c + 1
    out_fp.write("\n")

done = False
for line in in_fp:
    tokens = line.split()
    if not done and len(tokens) >= 3 and re.match('router1\[[0-9]\]', tokens[0]):
        c = 0
        for token in tokens:
            if c == 2:
                out_fp.write(" ttl_%d ->" % count)
                count = count + 1
            out_fp.write(" %s" % token)
            c = c + 1
        out_fp.write("\n")
    elif len(tokens) >= 2 and re.match('Local', tokens[1]):
        done = True
        out_fp.write(line)
    else:
        out_fp.write(line)
        
