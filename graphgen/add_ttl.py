#!/usr/bin/python

import sys
import re

if len(sys.argv) <= 2:
    # pylint: disable=superfluous-parens
    print("Usage %s <input file> <output file>\n")
    sys.exit(0)

IN_FP = open(str(sys.argv[1]), 'r')
OUT_FP = open(str(sys.argv[2]), 'w')

MAX_IF = 0
OLD_LINE = ""
for line in IN_FP:
    TOKENS = line.split()
    if len(TOKENS) >= 1 and re.match(r'\$\{if[0-9]\}_loss', TOKENS[0]):
        m = re.search('[0-9]', TOKENS[0])
        if m:
            val = int(m.group(0))
            if val > MAX_IF:
                MAX_IF = val
    elif len(TOKENS) >= 1 and re.match(r'router1\[[0-9]\]', TOKENS[0]):
        OLD_LINE = line
        break

    OUT_FP.write(line)

OUT_FP.write("\n//Dec TTL\n\n")
for ifs in range(MAX_IF):
    OUT_FP.write("ttl_%d :: DecIPTTL;\n" % (ifs + 1))
    OUT_FP.write(
        "ttl_%d[1] -> ICMPError(${if%d}:ip, timeexceeded) -> router1;\n" % ((ifs + 1), (ifs + 1))
    )

OUT_FP.write("\n")

COUNT = 1
TOKENS = OLD_LINE.split()
if len(TOKENS) >= 3 and re.match(r'router1\[[0-9]\]', TOKENS[0]):
    C = 0
    for token in TOKENS:
        if C == 2:
            OUT_FP.write(" ttl_%d ->" % COUNT)
            COUNT = COUNT + 1
        OUT_FP.write(" %s" % token)
        C = C + 1
    OUT_FP.write("\n")

DONE = False
for line in IN_FP:
    TOKENS = line.split()
    if not DONE and len(TOKENS) >= 3 and re.match(r'router1\[[0-9]\]', TOKENS[0]):
        C = 0
        for token in TOKENS:
            if C == 2:
                OUT_FP.write(" ttl_%d ->" % COUNT)
                COUNT = COUNT + 1
            OUT_FP.write(" %s" % token)
            C = C + 1
        OUT_FP.write("\n")
    elif len(TOKENS) >= 2 and re.match('Local', TOKENS[1]):
        done = True
        OUT_FP.write(line)
    else:
        OUT_FP.write(line)
