from ncclient import manager
import json
import networkx as nx
import re, socket

ROUTE_CONFIG_FILE = '/Users/diptsing/PycharmProjects/bbMainBranch/exabgp/config/routes.log'

class Node(object):
    _instance_track = []
    def __init__(self, node_name, router_id):
        self.node_name = node_name
        self.router_id = router_id
        self._instance_track.append(self)
        self.node_sid = None
        self.label_base = None
        self.label_range = None
        self.prefix_metric = {}

    def add_prefix_metric(self, prefix, metric):
        self.prefix_metric[prefix] = metric

    @classmethod
    def get_instance(cls):
        return cls._instance_track

def normalize_capacity(str_capacity):
    if re.search("Mbps", str_capacity):
        new = str_capacity.replace("Mbps","")
        return int(new)

def parse_db(json_ted_db):
    G = nx.MultiDiGraph()
    for item in json_ted_db['ted-database-information']:
        for router in item['ted-database']:
            node_name = router['ted-database-id'][0]['data']
            router_id = router['ted-database-lcl-addr'][0]['ted-lcl-addr'][0]['data']

            G.add_node(node_name)
            G.nodes[node_name]['router_id']=router_id
            G.nodes[node_name]['node_name'] = node_name

            for sr in router['ted-spring-capability']:
                G.nodes[node_name]['label_base'] = int(sr['ted-spring-srgb-block'][0]['ted-spring-srgb-block-start'][0]['data'])
                G.nodes[node_name]['label_range'] = int(sr['ted-spring-srgb-block'][0]['ted-spring-srgb-block-range'][0]['data'])
            for p in router['ted-prefixes']:
                PrefixSID = int(p['ted-prefix'][0]['ted-prefix-sid'][0]['ted-prefix-sid-index'][0]['data'])
                PrefixAddr = p['ted-prefix'][0]['ted-prefix-address'][0]['data']
                PrefixLen = p['ted-prefix'][0]['ted-prefix-length'][0]['data']
                G.nodes[node_name]['node_sid'] = PrefixSID + G.nodes[node_name]['label_base']

        for router in item['ted-database']:
            for link in router['ted-link']:
                local_ip = link['ted-link-local-address'][0]['data']
                remote_ip = link['ted-link-remote-address'][0]['data']
                igp_metric = int(link['ted-link-igp-metric'][0]['data'])
                link_bw = normalize_capacity(link['ted-link-static-bandwidth'][0]['data'])
                remote_node = link['ted-link-to'][0]['data']
                local_node = router['ted-database-id'][0]['data']
                G.add_edge(local_node, remote_node, weight=igp_metric, local_ip=local_ip, remote_ip=remote_ip, igp_metric=igp_metric, capacity=link_bw)

    return (G)

def parse_isis_db(json_isis_db):
    for isis_db in json_isis_db['isis-database-information']:
        for level in isis_db['isis-database']:
           pass

    return None

def check_capacity_graph(path, graph, constraint):
    i = 0
    j = 1
    while j < len(path):
        a_edge = path[i]
        b_edge = path[j]
        if graph.get_edge_data(a_edge, b_edge).get(0).get('capacity') < constraint:
            graph.remove_edge(a_edge, b_edge)
        i +=1
        j +=1
    return graph

def create_path(path, graph):
    destination = graph.nodes[path[-1]]['router_id']
    sr_list = []
    for p in path[2:]:
        sr_list.append(graph.nodes[p]['node_sid'])
    next_hop = graph.get_edge_data(path[0],path[1]).get(0).get('remote_ip')
    return (destination,next_hop,sr_list)

# 'neighbor 35.190.135.147 announce route 10.0.0.4 next-hop 10.0.1.7 label [ 800001 800004 ]'
def prep_routes(headend_ip, params):
    msg_body = str
    msg_body = 'neighbor '+ headend_ip + ' announce route '+ params[0]+' next-hop '+params[1]+ ' label '+ str(params[2]).replace(",","")
    return msg_body

def main():
    conn = manager.connect(host='mx3.pod1.nanog74.cloud.tesuto.com',username='tesuto',password='nanog74',
                           look_for_keys=False,allow_agent=False,device_params = {'name':'junos'},hostkey_verify=False)
    mx3_ip = socket.gethostbyname('mx3.pod1.nanog74.cloud.tesuto.com')
    result = conn.command('show ted database extensive', format='json')
    isis_db = conn.command('show isis database extensive', format='json')

    json_ted_db = json.loads(result.xpath('.')[0].text)
    json_isis_db = json.loads(isis_db.xpath('.')[0].text)


    flow_constraint_mx3 = 200
    flow_constraint_mx5 = 60
    dest_prefix = "10.1.1.4"

    graph_nodes = parse_db(json_ted_db)
    extract_prefix = parse_isis_db(json_isis_db)

    #mx3_mx4_spf = nx.shortest_path(graph_nodes, source='mx3.00(10.0.0.3)', target='mx1.00(10.0.0.1)', )
    #Problem 1
    shortest_path = nx.dijkstra_path(graph_nodes, 'mx3.00(10.0.0.3)', 'mx4.00(10.0.0.4)')
    # Problem 4
    edge_disjoint_paths = list(nx.edge_disjoint_paths(graph_nodes,'mx3.00(10.0.0.3)', 'mx4.00(10.0.0.4)'))

    #Problem 2
    residual_graph = check_capacity_graph(shortest_path, graph_nodes, constraint = flow_constraint_mx3)
    final_path2 = nx.dijkstra_path(residual_graph, 'mx3.00(10.0.0.3)', 'mx4.00(10.0.0.4)')

    get_params = create_path(final_path2, residual_graph)
    msg_body = prep_routes(mx3_ip, get_params)

    with open(ROUTE_CONFIG_FILE,'a') as fp:
        fp.write(msg_body+"\n")

    #spf2 = nx.dijkstra_path(residual_graph, 'mx5.00(10.0.0.5)', 'mx4.00(10.0.0.4)')
    #residual_graph2 = check_capacity_graph(spf2, residual_graph, constraint= flow_constraint_mx5)
    #print (nx.dijkstra_path(residual_graph2, 'mx5.00(10.0.0.5)', 'mx4.00(10.0.0.4)'))



if __name__ == "__main__":
    main()
    
