import networkx as nx
import re

def writeClick(g, args):
    filename = args.output
    
    numInputs = len(nx.get_node_attributes(g, 'ifs'))
    in_routers = []
    for node,ifs in nx.get_node_attributes(g, 'ifs').iteritems():
        edges = nx.edges(g, node)
        for edge in edges:
            if re.match("e[0-9]+", edge[0]):
                in_routers.append(int(edge[1]))
            else:
                in_routers.append(int(edge[0]))
    in_routers.sort()

    arpLess = True
    if args.arp:
        arpLess = False
        
    fh = open(filename, "w")

    writeRouters(fh, g)
    writeClassifiers(fh, numInputs)
    writePacketArrival(fh, numInputs)
    writePacketDeparture(fh, numInputs)
    if arpLess:
        writeARPLess(fh, numInputs)
    if not arpLess:
        writeARPHandler(fh, numInputs)
    writeLinkShaping(fh, g, args)
    writeTTLDec(fh, nx.edges(g))
    writeLinks(fh, g, args)
    writeDropPacketsOnRouters(fh, numInputs, in_routers)
    writeRoutersToInterfaces(fh, g, in_routers, arpLess)
    writeLocalDelivery(fh, g, nx.nodes(g), in_routers, arpLess)
    fh.close()

def writeClassifiers(fh, numInput):
    fh.write("\n// Packet Classifiers\n")
    for i in range(numInput):
        fh.write("c%d :: Classifier(12/0800, 12/0806 20/0001, 12/0806 20/0002, -);\n"
                 % (i + 1))
    fh.write("chost :: Classifier(12/0800, 12/0806 20/0001, 12/0806 20/0002, -);\n")

def writePacketArrival(fh, numInput):
    fh.write("\n// Packet Arrival\n")
    for i in range(numInput):
        fh.write("FromDevice(${if%d}) -> c%d;\n" % (i + 1, i + 1))
    fh.write("FromHost(fake0) -> chost;\n")

def writePacketDeparture(fh, numInput):
    fh.write("\n// Packet Departure\n")
    for i in range(numInput):
        fh.write("out%d :: ThreadSafeQueue() -> ToDevice(${if%d}, BURST 64);\n"
                 % (i + 1, i + 1))
        
            
def writeARPHandler(fh, numInput):
    fh.write("\n// Handle ARP\n")
    fh.write("arpt :: Tee(%d);\n\n" % (numInput + 1))
    for i in range(numInput):
        c = i + 1
        fh.write("c%d[1] -> ar%d :: ARPResponder(${if%d}:ip ${if%d}:eth) -> out%d;\n"
                 % (c, c, c, c, c))
        fh.write("arpq%d :: ARPQuerier(${if%d}:ip, ${if%d}:eth) -> out%d;\n"
                 % (c, c, c, c))
        fh.write("c%d[2] -> arpt;\n" % c)
        fh.write("arpt[%d] -> [1]arpq%d;\n\n" % (i, c))

    fh.write("chost[1] -> c1;\n")
    fh.write("chost[2] -> arpt;\n")

def writeARPLess(fh, numInput):
    fh.write("\n// Handle ARPless\n")
    for i in range(numInput):
        c = i + 1
        fh.write("al%d :: EtherEncap(0x0800, ${if%d}:eth, ${if%d_friend})\n" %
                 (c, c, c))

def writeDropPacketsOnRouters(fh, numInput, routers):
    fh.write("\n// Send IP Packets to Routers\n")
    for i in range(numInput):
        fh.write("c%d[0] -> Strip(14) -> CheckIPHeader(0) -> router%d;\n"
                 % (i + 1, routers[i]))
    fh.write("chost[0] -> Strip(14) -> CheckIPHeader(0) -> router%d;\n" % (routers[0]))
             
def writeRoutersToInterfaces(fh, g, routers, arpLess):
    numInputs = len(nx.get_node_attributes(g, 'ifs'))
    fh.write("\n// Send out packets to Interfaces\n")
    for i in range(numInputs):
        neighs = list(nx.all_neighbors(g, str(routers[i])))
        for neigh in neighs:
            if re.match("e[0-9]+", neigh):
                if not arpLess:
                    fh.write("router%d[%d] -> r%dttl_out -> [0]arpq%d;\n"
                             % (routers[i], neighs.index(neigh), i + 1, i + 1))
                else:
                    fh.write("router%d[%d] -> r%dttl_out -> al%d -> out%d;\n"
                             % (routers[i], neighs.index(neigh), i + 1, i + 1, i + 1))

def writeLinkShaping(fh, g, args):
    fh.write("\n// Link Traffic Shaping\n")
    edges = nx.edges(g)
    bws = nx.get_edge_attributes(g, 'bw')
    delays = nx.get_edge_attributes(g, 'delay')
    drops = nx.get_edge_attributes(g, 'drop')
    pull_elements = nx.get_edge_attributes(g, 'u_elements')
    push_elements = nx.get_edge_attributes(g, 'p_elements')
    for edge in edges:
        if re.match("e[0-9]+", edge[0]) or re.match("e[0-9]+", edge[1]):
            continue
        e0 = int(edge[0])
        e1 = int(edge[1])
        bw = args.bw
        delay = args.delay
        drop = args.loss
        if edge in bws:
            bw = bws[edge]
        if edge in delays:
            delay = delays[edge]
        if edge in drops:
            drop = delays[drop]

        qs = 1000
                    
        fh.write("link_%d_%d_queue :: ThreadSafeQueue(%d);\n" % (e0, e1, qs))
        fh.write("link_%d_%d_bw :: LinkUnqueue(%s, %s);\n" % (e0, e1, delay, bw))
        fh.write("link_%d_%d_loss :: RandomSample(DROP %s);\n" % (e0, e1, drop))
        fh.write("link_%d_%d_queue :: ThreadSafeQueue(%d);\n" % (e1, e0, qs))
        fh.write("link_%d_%d_bw :: LinkUnqueue(%s, %s);\n" % (e1, e0, delay, bw))
        fh.write("link_%d_%d_loss :: RandomSample(DROP %s);\n" % (e1, e0, drop))

        if edge in pull_elements:
            for element in pull_elements[edge]:
                tokens = element.split('(')
                fh.write("link_%d_%d_%s :: %s;\n" % (e0, e1, tokens[0], element))
                fh.write("link_%d_%d_%s :: %s;\n" % (e1, e0, tokens[0], element))
            
        if edge in push_elements:    
            for element in push_elements[edge]:
                tokens = element.split('(')
                fh.write("link_%d_%d_%s :: %s;\n" % (e0, e1, tokens[0], element))
                fh.write("link_%d_%d_%s :: %s;\n" % (e1, e0, tokens[0], element))

                 
def writeTTLDec(fh, edges):
    fh.write("\n// Decrement TTL and send time exceeded replies\n")
    for edge in edges:
        if re.match("e[0-9]+", edge[0]) or re.match("e[0-9]+", edge[1]):
            if re.match("e[0-9]+", edge[0]):
                edge = int(edge[1])
            else:
                edge = int(edge[0])
            fh.write("r%dttl_out :: DecIPTTL;\n" % edge)
            fh.write("r%dttl_out[1] -> ICMPError(10.100.150.%d, timeexceeded) -> router%d;\n" % (edge, edge, edge))
        else:
            e0 = int(edge[0])
            e1 = int(edge[1])
            fh.write("r%dttl_%d :: DecIPTTL;\n" % (e0, e1))
            fh.write("r%dttl_%d[1] -> ICMPError(10.100.150.%d, timeexceeded) -> router%d;\n" % (e0, e1, e0, e0))
            fh.write("r%dttl_%d :: DecIPTTL;\n" % (e1, e0))
            fh.write("r%dttl_%d[1] -> ICMPError(10.100.150.%d, timeexceeded) -> router%d;\n" % (e1, e0, e1, e1))

        
def writeRouters(fh, g):
    routes = nx.get_node_attributes(g, 'routes')
    node_ips = nx.get_node_attributes(g, 'ips')
    fh.write("\n// Routers\n")
    nodes = nx.nodes(g)
    nodes.sort()
    for node in nodes:
        if re.match("e[0-9]+", node):
            continue
        ifaces = routes[node]['ifaces']
        ips = routes[node]['ips']
        neighbors = list(nx.all_neighbors(g, node))
        first_str = "router%s :: RadixIPLookup(" % node
        last_str = ""
        middle_str = ""
        for iface,nhop in ifaces.iteritems():
            if re.match("e[0-9]+", nhop):
                last_str = "%s,\n                         ${%s_16} ${%s_gw} %d" % (last_str, iface, iface, neighbors.index(nhop))
                middle_str = "${%s}:ip %d" % (iface, len(neighbors))
                
            else:
                last_str = "%s,\n                         ${%s_16} %d" % (last_str, iface, neighbors.index(nhop))
        for ip, nhop in ips.iteritems():
            last_str = "%s,\n                         %s %d" % (last_str, ip, neighbors.index(nhop))
        last_str = "%s,\n                         %s %d" % (last_str, node_ips[node], len(neighbors))
        last_str = "%s);\n\n" % last_str
        if middle_str == "":
            last_str = last_str[27:]
        fh.write(first_str)
        fh.write(middle_str)
        fh.write(last_str)

def writeLinks(fh, g, args):
    fh.write("\n// Links\n")
    nodes = nx.nodes(g)
    nodes.sort()

    useCodel = args.useCodel
    
    for n in nodes:
        if re.match("e[0-9]+", n):
            continue
        neighbors = list(nx.all_neighbors(g, n))
        for ne in neighbors:
            if re.match("e[0-9]+", ne):
                continue

            pull_elements = g[n][ne]['s_elements']
            push_elements = g[n][ne]['l_elements']

            push_str = "->"
            pull_str = "->"

            codel = "->"
            if useCodel:
                codel = "-> CoDel() ->"
                
            for element in pull_elements:
                tokens = element.split("(")
                pull_str = "%s link_%s_%s_%s ->" % (pull_str, n, ne, tokens[0])

            for element in push_elements:
                tokens = element.split("(")
                push_str = "%s link_%s_%s_%s ->" % (push_str, n, ne, tokens[0])
            
            fh.write("router%s[%d] -> r%sttl_%s %s SetTimestamp(FIRST true) -> link_%s_%s_queue %s link_%s_%s_loss %s link_%s_%s_bw -> router%s\n"
                     % (n, neighbors.index(ne), n, ne, push_str, n, ne, codel, n, ne, pull_str, n, ne, ne))
        

def writeLocalDelivery(fh, g, routers, in_routers, arpLess):
    fh.write("\n// Local Delivery\n")
    fh.write("toh :: ToHost;\n\n")

    for router in routers:
        if not re.match("e[0-9]+", router):
            neighbors = list(nx.all_neighbors(g, str(router)))
            fh.write("router%s[%d] -> EtherEncap(0x0800, 1:1:1:1:1:1, 2:2:2:2:2:2) -> toh;\n"
                     % (router, len(neighbors)))

    if not arpLess:
        fh.write("arpt[%d] -> toh;\n" % len(routers))
    else:
        for router in in_routers:
            pos = in_routers.index(router) + 1
            fh.write("c%d[1] -> toh;\n" % pos)
            fh.write("c%d[2] -> toh;\n" % pos)
        fh.write("chost[1] -> Discard;\n")
        fh.write("chost[2] -> Discard;\n")
            
        
    fh.write("\n// Unknown packets to their death\n")
    for router in in_routers:
        pos = in_routers.index(router) + 1
        fh.write("c%d[3] -> Print(\"${if%d} Non IP\") -> Discard;\n"
                 % (pos, pos))

    fh.write("chost[3] -> Print(\"Host Non IP\") -> Discard;\n")
                 

    

