''' Scheduler.py '''
from abc import ABC, abstractmethod
from collections import Counter
from math import ceil

import matplotlib.pyplot as plt

import networkx as nx
from disk import Alias, Disk


class Scheduler(ABC):
    ''' Abstract class for implementing scheduling algorithms '''
    @abstractmethod
    def do_work(self, nodes, edges):
        ''' Run one round of the algorithm '''
        pass

    @abstractmethod
    def gen_edges(self, disks, graph):
        ''' Create list of edges '''
        pass
        
    def max_d(self, graph):
        ''' Return max cv d prime '''
        degrees = graph.degree()
        degrees = [ceil(d[1]/d[0].cv) for d in degrees]

        return max(degrees)

    def mg_split(self, graph):
        # Count occurence of edges
        occ = Counter(graph.edges())

        for e in occ:
            n = occ[e]
            while n > 1:
                # Create new edge using Alias of e[0]
                graph.add_edge(Alias(e[0]), e[1])

                # Remove old edge
                graph.remove_edge(e[0],e[1])

                n -= 1

class InOrder(Scheduler):
    ''' Perform transmission between disk in order present in list '''
    def gen_edges(self, graph):
        return [e for e in graph.edges()]

    def do_work(self, graph, queue):
        working = []
        for e in queue:
            if e[0].avail > 0 and e[1].avail > 0 and graph.has_edge(e[0], e[1]):
                if e[0] != e[1]:
                    # Aqcuire cv resources
                    e[0].acquire()
                    e[1].acquire()

                    # Remove work
                    graph.remove_edge(e[0],e[1])

                    # Assign disk to active pool
                    working.append(e[0])
                    working.append(e[1])

                    print("Disk" + str(e[0]) + " transferring to Disk" + str(e[1]))
                else:
                    e[0].acquire()
                    graph.remove_edge(e[0],e[1])
                    working.append(e[0])
                    print("Disk" + str(e[0]) + " transferring to Disk" + str(e[1]))

        # Free resources
        for w in working:
            w.free()

class EdgeRanking(InOrder):
    ''' Performs transmission between disks using greedy alg to generate list of edges for InOrder '''
    def gen_edges(self, graph):
        degrees = self.dv_cv(graph) 
        
        # Compute dvcv weight of each edge
        weighted = [(degrees[edge[0]] + degrees[edge[1]], edge) for edge in graph.edges()]

        # Return list of edges of descending accumlative dvcv score
        return [edge for _, edge in sorted(weighted, key=lambda value: value[0])]

    def dv_cv(self, graph):
        ''' Return degree/cv of disks for current round '''
        degrees = graph.degree()

        return {d[0]:ceil(d[1]/d[0].cv) for d in degrees}

class FlattenAndColor(InOrder):
    ''' Temp scheduler to test coloring '''
    def __init__(self):
        self.a_graph = None
        self.e_colors = None

    def gen_edges(self, graph):
        if not self.a_graph:
            # Generate alias graph
            self.a_graph = self.split(graph)
            self.e_colors = [e for e in self.greedy_color(self.a_graph).items()]

        # Return edges for round
        return [(e[0].org, e[1].org) for e, _ in sorted(self.e_colors, key=lambda item: item[1])]

    def alias_graph(self, graph):
        a = nx.MultiGraph()

        for d in graph.nodes():
            # Create alias disk
            disk_alias = Alias(d)

            # Copy edges from original
            edges = graph.edges(d)
            alias_edges =[(disk_alias, Alias(e[1])) for e in edges]
            
            # Add to alias graph
            a.add_node(disk_alias)
            a.add_edges_from(alias_edges)

        return a

    def split(self, graph):
        ''' Split nodes into d.cv alias nodes with identical edges '''
        self.a_graph = self.alias_graph(graph)

        new_disks = []
        new_edges = []
        for d in self.a_graph.nodes():
            if d.org.cv > 1:
                edges = self.a_graph.edges(d)
                
                # Create d.cv number of clones with  a cv of 1
                for i in range(1,d.org.cv-1):
                    new_d = Alias(d.org)
                    new_edges = [(new_d, e[1]) for e in edges]

        # Append cv clones
        self.a_graph.add_nodes_from(new_disks)
        self.a_graph.add_edges_from(new_edges)
  
        return self.a_graph

    def greedy_color(self, graph):
        e_colors = {}
        d_colors = {}
        for d in graph.nodes():
            adj = []

            color = 0
            for e in graph.edges(d):
                if e not in e_colors:
                    e_colors[e] = color
                    color += 1

        return e_colors

class Bipartite(InOrder):
    ''' Chadi algorithm scheduler '''
    def __init__(self):
        self.normalized = False
        self.b = None

    def gen_edges(self, graph):
        ''' Build bipartite graph '''
        # Normalize
        if not self.normalized:
            # Relax CV
            for d in graph:
                if d.cv%2:
                    d.cv -= 1
                    d.avail -= 1

            #self.mg_split(graph)
            self.normalize(graph)
            self.normalized = True

            # Euler cycle
            ec = nx.eulerian_circuit(graph)

            # Remove self-loops on graph
            loops = []
            for e in graph.edges():
                if e[0].org is e[1].org:
                    loops.append(e)

            graph.remove_edges_from(loops)

            # Bipartite graph for flow problem, NOTE: cannot express MG characteristics
            self.b = nx.DiGraph()

            # v-in aliases and edge mapping
            v_out = [d for d in graph.nodes()]
            v_in = {d:Alias(d) for d in graph.nodes()}

            # Added edges in euler cycle with capacity of 1
            c=0
            for e in ec:
                self.b.add_edge(e[0], v_in[e[1]], capacity=1)

                if e[0].org is not e[1].org:
                    c +=1 

            # Create s-node
            self.b.add_node('t')
            for d in v_in.items():
                self.b.add_edge(d[1], 't', capacity=ceil(d[1].org.cv/2))

            # Create t-node
            self.b.add_node('s')
            for d in v_out:
                self.b.add_edge('s', d, capacity=ceil(d.cv/2))

        # Ford-Fulkerson flow Returns: (flow_val, flow_dict)
        _, flow_dict = nx.maximum_flow(self.b, 's', 't')

        # Extract active edges and cull self loops and s/t nodes
        flow = [(d[0], d2[0]) for d in flow_dict.items() for d2 in d[1].items() \
                if d2[1] > 0 and d[0] not in ['s','t'] and d2[0] not in ['s','t']]
        
        self.b.remove_edges_from(flow)

        # Reassociate aliases and return queue
        return [(e[0].org, e[1].org) for e in flow if e[0].org is not e[1].org]

    def normalize(self, graph):
        ''' Add self loops to normalize cv d prime '''
        delta_prime = self.max_d(graph)

        spares = []
        for d in graph.nodes():            
            while graph.degree(d) < (delta_prime*d.cv)-1:
                graph.add_edge(d, d)

            # Identify nodes with odd degree
            if graph.degree(d) == delta_prime*d.cv-1:
                spares.append(d)

        # Pair nodes with delta*cv - 1
        while spares:
            new_edge = spares[:2]
            spares = spares[2:]

            graph.add_edge(new_edge[0], new_edge[1])

class Greedy(FlattenAndColor):
    ''' Split disk Cv and return maximal matching each round '''
    def __init__(self):
        self.a_graph = None

    def do_work(self, graph, queue):
        if not queue:
            graph.clear()
        else:
            for e in queue:
                print("Disk" + str(e[0]) + " transferring to Disk" + str(e[1]))

    def gen_edges(self, graph):
        # Split Cv and generate alias graph
        if not self.a_graph:
            self.a_graph = self.split(graph)

        # Solve max matching to obtain round
        queue = nx.maximal_matching(self.a_graph)

        # Cull active edges
        self.a_graph.remove_edges_from(queue)

        # Reassociate aliases
        return [(e[0].org, e[1].org) for e in queue]
