import networkx as nx
__NX_VERSION__ = int(nx.__version__.split('.')[0])
import re, time

class ClickGen():
    def __init__(self, g, args, cmdline):
        self.g = g
        self.args = args
        self.cmdline = cmdline

    def getCapitalLetters(self, in_str):
        out_str = ""
        for c in in_str:
            if c.isupper():
                out_str += c

        return out_str
        
    def writeClick(self, g, args):
        self.g = g
        self.args = args

        filename = self.args.output
    
        self.numInputs = len(nx.get_node_attributes(self.g, 'ifs'))
        self.numOthers = len(nx.get_node_attributes(self.g, 'others'))
        self.in_routers = []
        for node,ifs in nx.get_node_attributes(self.g, 'ifs').iteritems():
            edges = nx.edges(self.g, node)
            for edge in edges:
                if re.match("e[0-9]+", edge[0]) or re.match("o[0-9]+", edge[0]):
                    self.in_routers.append(int(edge[1]))
                else:
                    self.in_routers.append(int(edge[0]))
        self.in_routers.sort()
        self.g_in_routers = list(nx.get_node_attributes(self.g, 'in_routers').values())
        self.g_in_routers.sort(key=lambda x: int(re.search('[0-9]+', x[0]).group(0)))

        self.arpLess = True
        self.useDPDK = args.useDPDK
        
        # DPDK must use ARP
        if args.arp or args.useDPDK:
            self.arpLess = False
        
        self.fh = open(filename, "w")

        self.writePreamble()
        self.writeRouters()
        self.writeClassifiers()
        if args.useDPDK:
            self.writeVLANMultiplexing()
        self.writePacketArrival()
        self.writePacketDeparture()
        if self.arpLess:
            self.writeARPLess()
        if not self.arpLess:
            self.writeARPHandler()
        self.writeLinkShaping()
        self.writeTTLDec()
        self.writeLinks()
        self.writeTeedLinks()
        self.writeDropPacketsOnRouters()
        self.writeRoutersToInterfaces()
        self.writeLocalDelivery()
        self.fh.close()

    def writePreamble(self):
        tstr = time.asctime(time.gmtime(time.time()))

        self.fh.write("// Auto generated Click Template using GraphGen/clickGen.py at %s UTC" % tstr)
        if self.cmdline:
            self.fh.write("\n// Command line: %s \n\n" % dict(self.cmdline))

        
    def writeClassifiers(self):
        self.fh.write("\n// Packet Classifiers\n")
        i = 1
        in_routers = self.g_in_routers
        # Create classifiers
        for nodes in in_routers:
            for node in nodes:
                self.fh.write("c%d :: Classifier(12/0800, 12/0806 20/0001, 12/0806 20/0002, -);\n"
                              % int(re.search('[0-9]+', node).group(0)))
                i = i + 1
        self.fh.write("chost :: Classifier(12/0800, 12/0806 20/0001, 12/0806 20/0002, -);\n")

    def writeVLANMultiplexing(self):
        self.fh.write("\n// VLAN Multiplexing\n")
        in_routers = self.g_in_routers
        vlanstr = ""
        for router_list in in_routers:
            for router in router_list:
                vlanstr = "%s, VLAN ${vlan%d}" % (vlanstr, (int(re.search('[0-9]+', router).group(0))))
        vlanstr = vlanstr[2:]
        self.fh.write("vlanmux :: VlanSwitch(%s);\n" % vlanstr)
    
    def writePacketArrival(self):
        self.fh.write("\n// Packet Arrival\n")
        in_routers = self.g_in_routers
        if self.useDPDK:
            self.fh.write("$DPDKArrival\n")

            i = 0
            # FIX DO THIS RIGHT!  We'll start with just the standard mode
            for router_list in in_routers:
                for router in router_list:
                    self.fh.write("vlanmux[%d] -> c%d;\n" % (i, int(re.search('[0-9]+', router).group(0))))
                    i = i + 1
                            
        else:
            # FIX THIS TOO, for MULTI HOMING
            c = 1
            for router in in_routers:
                self.fh.write("FromDevice(${if%d}) -> c%d;\n" % (int(re.search('[0-9]+', router).group(0)), c))
                c = c + 1
            for i in range(self.numOthers):
                self.fh.write("FromDevice(${ifo%d}) -> c%d;\n" % (i + 1, c))
                c = c + 1
                     
        self.fh.write("FromHost(fake0) -> chost;\n")

    # WE'RE HERE
    # NEED TO COMPLETELY RETHINK DPDK and INPUT/OUTPUT implementation
        
    def writePacketDeparture(self):
        self.fh.write("\n// Packet Departure\n")
        in_routers = self.g_in_routers
        if self.useDPDK:
            self.fh.write("$DPDKDeparture\n")
            i = 0
            for router_list in in_routers:
                for router in router_list:
                    r = (int(re.search('[0-9]+', router).group(0)))
                    self.fh.write("out%d :: VLANEncap(${vlan%d}) -> ${out_if%d};\n"
                                  % (r, r, r))
                    i = i + 1
        
        else:
            # FIX NON DPDK
            c = 1
            for router in in_routers:
                self.fh.write("out%d :: ThreadSafeQueue() -> ToDevice(${if%d}, BURST 64);\n"
                              % (c, int(re.search('[0-9]+', router).group(0))))
                c = c + 1
            for i in range(self.numOthers):
                self.fh.write("out%d :: ThreadSafeQueue() -> ToDevice(${ifo%d}, BURST 64);\n"
                              % (c, i + 1))
                c = c + 1
        
            
    def writeARPHandler(self):
        self.fh.write("\n// Handle ARP\n")
        in_routers = list(nx.get_node_attributes(self.g, 'in_routers').values())
        in_routers.sort(key=lambda x: int(re.search('[0-9]+', x[0]).group(0)))
        t = 1
        for router_list in in_routers:
            t = t + len(router_list)
        
        self.fh.write("arpt :: Tee(%d);\n\n" % t)
        i = 1
        # FIX HTIS TOO
        for router_list in in_routers:
            for router in router_list:
                c = int(re.search('[0-9]+', router).group(0))
                if self.args.useDPDK:
                    self.fh.write("c%d[1] -> ar%d :: ARPResponder(${if%d_ip} ${if%d_eth}) -> out%d;\n"
                                  % (c, c, c, c, c))
                    self.fh.write("arpq%d :: ARPQuerier(${if%d_ip}, ${if%d_eth}) -> out%d;\n"
                                  % (c, c, c, c))
                else:
                    self.fh.write("c%d[1] -> ar%d :: ARPResponder(${if%d}:ip ${if%d}:eth) -> out%d;\n"
                                  % (i, i, c, c, i))
                    self.fh.write("arpq%d :: ARPQuerier(${if%d}:ip, ${if%d}:eth) -> out%d;\n"
                                  % (i, c, c, i))
                self.fh.write("c%d[2] -> arpt;\n" % c)
                self.fh.write("arpt[%d] -> [1]arpq%d;\n\n" % (i - 1, c))
                i = i + 1

        self.fh.write("chost[1] -> c1;\n")
        self.fh.write("chost[2] -> arpt;\n")

    def writeARPLess(self):
        self.fh.write("\n// Handle ARPless\n")
        x = 1
        c = 1
        in_routers = list(nx.get_node_attributes(self.g, 'in_routers').values())
        in_routers.sort(key=lambda x: int(re.search('[0-9]+', x).group(0)))
        for router in in_routers:
            if_n = int(re.search('[0-9]+', router).group(0))
            self.fh.write("al%d :: EtherEncap(0x0800, ${if%d}:eth, ${if%d_friend})\n" %
                          (c, if_n, if_n))
            c = c + 1
            x = x + 1
        for i in range(self.numOthers):
            c = i + 1
            self.fh.write("al%d :: EtherEncap(0x0800, ${ifo%d}:eth, ${ifo%d_friend})\n" %
                          (x, c, c))
            x = x + 1

    def writeDropPacketsOnRouters(self):
        self.fh.write("\n// Send IP Packets to Routers\n")
        in_routers = nx.get_node_attributes(self.g, 'in_routers')
        
        bw = self.args.bw
        delay = self.args.delay
        drop = self.args.loss
        qs = 1000
        
        for router, router_list in in_routers.iteritems():
            for router_iface in router_list:
                iface = int(re.search('[0-9]+', router_iface).group(0))
                if self.args.inConstraints:
                    # should check if we have overrides
                    self.fh.write("link_in_%d_queue :: ThreadSafeQueue(%d);\n" % (iface, qs))
                    self.fh.write("link_in_%d_bw :: LinkUnqueue(%s, %s);\n" % (iface, delay, bw))
                    self.fh.write("link_in_%d_loss :: RandomSample(DROP %s);\n" % (iface, drop))
                    
                    self.fh.write("c%d[0] -> Strip(14) -> CheckIPHeader(0) -> link_in_%d_queue -> CoDel() -> link_in_%d_loss -> link_in_%d_bw -> router%s;\n"
                                  % (iface, iface, iface, iface, router))
                else:
                    self.fh.write("c%d[0] -> Strip(14) -> CheckIPHeader(0) -> router%s;\n"
                                  % (iface, router))
        self.fh.write("chost[0] -> Strip(14) -> CheckIPHeader(0) -> router%d;\n" % (self.in_routers[0]))
             
    def writeRoutersToInterfaces(self):
        in_routers = nx.get_node_attributes(self.g, 'in_routers')
        numInputs = len(in_routers)
        self.fh.write("\n// Send out packets to Interfaces\n")
        tmp_list = list(set(self.in_routers))

        bw = self.args.bw
        delay = self.args.delay
        drop = self.args.loss
        qs = 1000
        
        for i in range(numInputs):
            neighs = list(nx.all_neighbors(self.g, str(tmp_list[i])))
            neighs.sort(key=lambda x: int(re.search('[0-9]+', x).group(0)))
            c = 0
            for neigh in neighs:
                if re.match("[oe][0-9]+", neigh):
                    if not self.arpLess:
                        inputs = in_routers[str(tmp_list[i])]
                        iface = int(re.search('[0-9]+', inputs[c]).group(0))
                        if self.args.inConstraints:
                            self.fh.write("link_out_%d_queue :: ThreadSafeQueue(%d);\n" % (iface, qs))
                            self.fh.write("link_out_%d_bw :: LinkUnqueue(%s, %s);\n" % (iface, delay, bw))
                            self.fh.write("link_out_%d_loss :: RandomSample(DROP %s);\n" % (iface, drop))
                            
                            self.fh.write("router%d[%d] -> r%dttl_out_%s -> link_out_%d_queue -> CoDel() -> link_out_%d_loss -> link_out_%d_bw -> arpq%d;\n"
                                          % (tmp_list[i], neighs.index(neigh), tmp_list[i], neigh, iface, iface, iface, iface))
                        else:
                            self.fh.write("router%d[%d] -> r%dttl_out_%s -> arpq%d;\n"
                                          % (tmp_list[i], neighs.index(neigh), tmp_list[i], neigh, int(re.search('[0-9]+', inputs[c]).group(0))))
                        c = c + 1
                    else:
                        #fix this later, see above
                        self.fh.write("router%d[%d] -> r%dttl_out_%s -> al%d -> out%d;\n"
                                      % (self.in_routers[i], neighs.index(neigh), self.in_routers[i], neigh, i + 1, i + 1))

    def writeLinkShaping(self):
        self.fh.write("\n// Link Traffic Shaping\n")
        edges = nx.edges(self.g)
        tees = nx.get_edge_attributes(self.g, 'tee')
        bws = nx.get_edge_attributes(self.g, 'bw')
        delays = nx.get_edge_attributes(self.g, 'delay')
        drops = nx.get_edge_attributes(self.g, 'drop')
        losses = nx.get_edge_attributes(self.g, 'loss')
        pull_elements = nx.get_edge_attributes(self.g, 'l_elements')
        push_elements = nx.get_edge_attributes(self.g, 's_elements')
        for edge in edges:
            if re.match("[oe][0-9]+", edge[0]) or re.match("[oe][0-9]+", edge[1]):
                continue
            e0 = int(edge[0])
            e1 = int(edge[1])
            bw = self.args.bw
            delay = self.args.delay
            drop = self.args.loss
            if edge in bws:
                bw = bws[edge]
            if edge in delays:
                delay = delays[edge]
            if edge in drops:
                drop = drops[edge]
            elif edge in losses:
                drop = losses[edge]

            qs = 1000
                    
            self.fh.write("link_%d_%d_queue :: ThreadSafeQueue(%d);\n" % (e0, e1, qs))
            self.fh.write("link_%d_%d_bw :: LinkUnqueue(%s, %s);\n" % (e0, e1, delay, bw))
            self.fh.write("link_%d_%d_loss :: RandomSample(DROP %s);\n" % (e0, e1, drop))
            self.fh.write("link_%d_%d_queue :: ThreadSafeQueue(%d);\n" % (e1, e0, qs))
            self.fh.write("link_%d_%d_bw :: LinkUnqueue(%s, %s);\n" % (e1, e0, delay, bw))
            self.fh.write("link_%d_%d_loss :: RandomSample(DROP %s);\n" % (e1, e0, drop))

            if edge in pull_elements:
                for element in pull_elements[edge]:
                    tokens = element.split('(')
                    element_short = self.getCapitalLetters(tokens[0])
                    self.fh.write("link_%d_%d_%s :: %s;\n" % (e0, e1, element_short, element))
                    self.fh.write("link_%d_%d_%s :: %s;\n" % (e1, e0, element_short, element))
            
            if edge in push_elements:    
                for element in push_elements[edge]:
                    tokens = element.split('(')
                    element_short = self.getCapitalLetters(tokens[0])
                    self.fh.write("link_%d_%d_%s :: %s;\n" % (e0, e1, element_short, element))
                    self.fh.write("link_%d_%d_%s :: %s;\n" % (e1, e0, element_short, element))

            if edge in tees:
                self.fh.write("link_%d_%d_tee :: Tee(2);\n" % (e0, e1))
                self.fh.write("link_%d_%d_tee :: Tee(2);\n" % (e1, e0))

                 
    def writeTTLDec(self):
        self.fh.write("\n// Decrement TTL and send time exceeded replies\n")
        edges = nx.edges(self.g)
        for edge in edges:
            if re.match("[oe][0-9]+", edge[0]) or re.match("[oe][0-9]+", edge[1]):
                if re.match("[oe][0-9]+", edge[0]):
                    out = edge[0]
                    edge = int(edge[1])
                else:
                    out = edge[1]
                    edge = int(edge[0])
                self.fh.write("r%dttl_out_%s :: DecIPTTL;\n" % (edge, out))
                self.fh.write("r%dttl_out_%s[1] -> ICMPError(10.100.150.%d, timeexceeded) -> router%d;\n" % (edge, out, edge, edge))
            else:
                e0 = int(edge[0])
                e1 = int(edge[1])
                self.fh.write("r%dttl_%d :: DecIPTTL;\n" % (e0, e1))
                self.fh.write("r%dttl_%d[1] -> ICMPError(10.100.150.%d, timeexceeded) -> router%d;\n" % (e0, e1, e0, e0))
                self.fh.write("r%dttl_%d :: DecIPTTL;\n" % (e1, e0))
                self.fh.write("r%dttl_%d[1] -> ICMPError(10.100.150.%d, timeexceeded) -> router%d;\n" % (e1, e0, e1, e1))

        
    def writeRouters(self):
        routes = nx.get_node_attributes(self.g, 'routes')
        node_ips = nx.get_node_attributes(self.g, 'ips')
        self.fh.write("\n// Routers\n")

        if __NX_VERSION__ > 1:
            nodes = nx.nodes(self.g).keys()
        else:
            nodes = nx.nodes(self.g)
        nodes.sort()
        in_routers = nx.get_node_attributes(self.g, 'in_routers')
    
        for node in nodes:
            if re.match("[oe][0-9]+", node):
                continue
            ifaces = routes[node]['ifaces']
            ips = routes[node]['ips']
            neighbors = list(nx.all_neighbors(self.g, node))
            neighbors.sort(key=lambda x: int(re.search('[0-9]+', x).group(0)))
            first_str = "router%s :: RadixIPLookup(" % node
            last_str = ""
            middle_str = ""
            for iface,nhop in ifaces.iteritems():
                if node in in_routers and iface in in_routers[node]:
                    last_str = "%s,\n                         ${%s_16} ${%s_gw} %d" % (last_str, iface, iface, neighbors.index(nhop))
                    if self.args.useDPDK:
                        middle_str = "${%s_ip} %d,\n                         %s" % (iface, len(neighbors), middle_str)
                    else:
                        middle_str = "${%s}:ip %d" % (iface, len(neighbors))
                                                
                else:
                    last_str = "%s,\n                         ${%s_16} %d" % (last_str, iface, neighbors.index(nhop))
            for ip, nhop in ips.iteritems():
                last_str = "%s,\n                         %s %d" % (last_str, ip, neighbors.index(nhop))
            last_str = "%s,\n                         %s %d" % (last_str, node_ips[node], len(neighbors))
            last_str = "%s);\n\n" % last_str
            if middle_str == "":
                last_str = last_str[27:]
            else:
                middle_str = middle_str.strip(',\n ')
            self.fh.write(first_str)
            self.fh.write(middle_str)
            self.fh.write(last_str)

    def writeLinks(self):
        self.fh.write("\n// Links\n")
        if __NX_VERSION__ > 1:
            nodes = nx.nodes(self.g).keys()
        else:
            nodes = nx.nodes(self.g)
        nodes.sort()

        useCodel = self.args.useCodel
    
        for n in nodes:
            if re.match("[oe][0-9]+", n):
                continue
            neighbors = list(nx.all_neighbors(self.g, n))
            neighbors.sort(key=lambda x: int(re.search('[0-9]+', x).group(0)))

            for ne in neighbors:
                if re.match("[oe][0-9]+", ne):
                    continue

                pull_elements = self.g[n][ne]['l_elements']
                push_elements = self.g[n][ne]['s_elements']

                push_str = "->"
                pull_str = "->"
                tee_str = "->"

                codel = "->"
                if useCodel:
                    codel = "-> CoDel() ->"
                
                for element in pull_elements:
                    tokens = element.split("(")
                    element_short = self.getCapitalLetters(tokens[0])
                    pull_str = "%s link_%s_%s_%s ->" % (pull_str, n, ne, element_short)
                
                for element in push_elements:
                    tokens = element.split("(")
                    element_short = self.getCapitalLetters(tokens[0])
                    push_str = "%s link_%s_%s_%s ->" % (push_str, n, ne, element_short)

                if 'tee' in self.g[n][ne]:
                    tee_str = "-> link_%s_%s_tee ->" % (n, ne)
                
                self.fh.write("router%s[%d] -> r%sttl_%s %s SetTimestamp(FIRST true) -> link_%s_%s_queue %s link_%s_%s_loss %s link_%s_%s_bw %s router%s\n"
                              % (n, neighbors.index(ne), n, ne, push_str, n, ne, codel, n, ne, pull_str, n, ne, tee_str, ne))
        

    def writeTeedLinks(self):
        tees = nx.get_edge_attributes(self.g, 'tee')
        self.fh.write("\n // Teed Inputs and Outputs\n")
        self.fh.write("\n // Input from Teed interfaces is discarded\n")
        c = self.numOthers + 1
        for edge in tees:
            self.fh.write("FromDevice(${ifo%d}) -> Discard;\n" % (c))
            c = c + 1

        self.fh.write("\n// Output Chains\n")
        c = self.numOthers + 1
        k = self.numInputs + 1
    
        for edge in tees:
            self.fh.write("link_%s_%s_tee[1] -> al%d :: EtherEncap(0x0800, ${ifo%d}:eth, ${ifo%d_friend})\n" % (edge[0], edge[1], k, c, c))
            self.fh.write("link_%s_%s_tee[1] -> al%d;\n" % (edge[1], edge[0], k))
            c = c + 1
            k = k + 1

        k = self.numInputs + 1
        c = self.numOthers + 1

        for edge in tees:
            self.fh.write("al%d -> ThreadSafeQueue() -> ToDevice(${ifo%d});\n" %
                          (k, c))
            k = k + 1
            c = c + 1
        
    def writeLocalDelivery(self):
        self.fh.write("\n// Local Delivery\n")
        if self.args.useDPDK:
            self.fh.write("toh :: ToHost(fake0);\n\n")
        else:
            self.fh.write("toh :: ToHost;\n\n")
        if __NX_VERSION__ > 1:
            routers = nx.nodes(self.g).keys()
        else:
            routers = nx.nodes(self.g)
        for router in routers:
            if not re.match("[oe][0-9]+", router):
                neighbors = list(nx.all_neighbors(self.g, str(router)))
                self.fh.write("router%s[%d] -> EtherEncap(0x0800, 1:1:1:1:1:1, 2:2:2:2:2:2) -> toh;\n"
                              % (router, len(neighbors)))

        if not self.arpLess:
            self.fh.write("arpt[%d] -> toh;\n" % len(self.in_routers))
        else:
            for router in self.in_routers:
                pos = self.in_routers.index(router) + 1
                self.fh.write("c%d[1] -> toh;\n" % pos)
                self.fh.write("c%d[2] -> toh;\n" % pos)
            self.fh.write("chost[1] -> Discard;\n")
            self.fh.write("chost[2] -> Discard;\n")
            
        
        self.fh.write("\n// Unknown packets to their death\n")
        in_rtr = list(nx.get_node_attributes(self.g, 'in_routers').values())
        in_rtr.sort(key=lambda x: int(re.search('[0-9]+', x[0]).group(0)))
        for router_list in in_rtr:
            for router in router_list:
                pos = int(re.search('[0-9]+', router).group(0))
                self.fh.write("c%d[3] -> Print(\"${if%d} Non IP\") -> Discard;\n"
                              % (pos, pos))
                
        self.fh.write("chost[3] -> Print(\"Host Non IP\") -> Discard;\n")
                 

    

