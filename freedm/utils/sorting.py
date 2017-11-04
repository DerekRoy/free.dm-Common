'''
General utilities to sort data structures
@author: Thomas Wanderer
'''

# Imports
from functools import reduce

# Define custom Exception
class CyclicReference(Exception):
    """An exception thrown when items define a cyclic dependency that cannot be resolved"""

def topologicalSorter(data):
    """
    This function returns a list of topologically ordered items (Dependency graph) of dictionary 
    items which define dependency among themselves. The functions throws an error 
    if a cyclic dependency is found. The data needs to be provided in the following form:
    
    data = {
        'A': set(),
        'D': set(['A', 'C']),
        'C': set(['B']),
        'B': set(['A'])
    }
    :param dict: The data structure
    :returns: A topologically ordered list
    :rtype: list
    """
    
    def sort(data):
        # Ignore item self-references
        for k, v in data.items():
            v.discard(k)
            
        # Find and add foreign items
        foreign_items = reduce(set.union, data.values()) - set(data.keys())
        data.update({item:set() for item in foreign_items})
        
        # Sort topologically (Dependency graph)
        while True:
            ordered = set(item for item,dep in data.items() if not dep)
            if not ordered:
                break
            yield ' '.join(sorted(ordered))
            data = {item: (dep - ordered) for item,dep in data.items() if item not in ordered}
        try:
            assert not data, 'A cyclic dependency exists amongst {}'.format(data)
        except AssertionError as e:
            raise CyclicReference(e)
        
    graph = ' '.join([i for i in sort(data)]).split(' ')
    return [g for g in graph if g in data]