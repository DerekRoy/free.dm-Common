'''
This module defines a generic IPC protocol to be used between ICP servers and clients
Subclass from this class to create a custom IPC protocol for servers and clients.
@author: Thomas Wanderer
'''


class Protocol(object):
    
    version: None
    
    def supports(self):
        pass
    
    
# Sollten settings based sein, also settings das Protokoll verhalten beeinflussen
# 
# Base protocols
# 
# Protocols sollen rpc oder topic based sein, also entweder eine rpc API anbieten oder einfach nur ein Public subscribe anbieten
# 
# Brauchen evtl. Einen internen state?
# 
# Sollten Versioniert werden können
# 
# Standard dekoratoren für Services oder amdereechanismen sollten erlauben schnell ein Protokoll aufzusetzen.
# 
# Für unterschiedliche Einsatzzwecke. Einmal Unidirectional oder bidirektional.
# 
# Brauchen message queue und evtl. Ein adressier system