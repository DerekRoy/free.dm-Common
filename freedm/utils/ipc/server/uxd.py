'''
This module defines an IPC server communicating via UXD sockets
@author: Thomas Wanderer
'''

try:
    # Imports
    import os
    import asyncio
    import socket
    import struct
    import time
    from pathlib import Path
    from typing import Union, Type, Optional, TypeVar
    
    # free.dm Imports
    from freedm.utils.ipc.server.base import IPCSocketServer
    from freedm.utils.ipc.exceptions import freedmIPCSocketCreation, freedmIPCSocketShutdown
    from freedm.utils.ipc.connection import Connection, ConnectionType
    from freedm.utils.ipc.protocol import Protocol
except ImportError as e:
    from freedm.utils.exceptions import freedmModuleImport
    raise freedmModuleImport(e)


US = TypeVar('US', bound='UXDSocketServer')


class UXDSocketServer(IPCSocketServer):
    '''
    An IPC server using Unix Domain sockets implemented as async contextmanager.
    '''
    
    def __init__(
            self,
            path: Union[str, Path]=None,
            loop: Optional[Type[asyncio.AbstractEventLoop]]=None,
            limit: Optional[int]=None,
            chunksize: Optional[int]=None,
            max_connections: Optional[int]=None,
            mode: Optional[ConnectionType]=None,
            protocol: Optional[Protocol]=None
            ) -> None:
        
        super(self.__class__, self).__init__(loop, limit, chunksize, max_connections, mode, protocol)
        self.path = path

    async def __aenter__(self) -> US:
        if not self.path:
            raise freedmIPCSocketCreation('Cannot create UXD socket (No socket file provided)')
        elif os.path.exists(self.path):
            if os.path.isdir(self.path):
                try:
                    os.rmdir()
                except:
                    raise freedmIPCSocketCreation(f'Cannot create UXD socket because "{self.path}" is a directory ({e})')
            else:
                try:
                    os.remove(self.path)
                except Exception as e:
                    raise freedmIPCSocketCreation(f'Cannot delete UXD socket file "{self.path}" ({e})')
        try:
            # Create UXD socket (Based on https://www.pythonsheets.com/notes/python-socket.html)
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.bind(self.path)
        except Exception as e:
            raise freedmIPCSocketCreation(f'Cannot create UXD socket file "{self.path}" ({e})')
        
        # Create UDP socket server
        if self.limit:
            server = await asyncio.start_unix_server(self._onConnectionEstablished, loop=self.loop, sock=sock, limit=self.limit)
        else:
            server = await asyncio.start_unix_server(self._onConnectionEstablished, loop=self.loop, sock=sock)
        self._server = server
            
        # Return self
        return self

    async def __aexit__(self, *args) -> None:
        # Call parent method to make sure all pending connections are being cancelled
        await super(self.__class__, self).__aexit__()
        # Stop the server and remove UXD socket
        try:
            self._server.close()
        except Exception as e:
            self.logger.error('Cannot close IPC UXD socket server', self._server, e)
        try:   
            await self._server.wait_closed()
        except Exception as e:
            self.logger.error('Could not wait until IPC UXD server closed', self._server, e)    
        try:
            os.remove(self.path)
        except Exception as e:
            raise freedmIPCSocketShutdown(e)
        self.logger.debug(f'IPC server closed (UXD socket "{self.path}")')
        
    def _assembleConnection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> Connection:
        sock = writer.get_extra_info('socket')
        credentials = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i'))
        pid, uid, gid = struct.unpack('3i', credentials)
        return Connection(
            socket=sock,
            pid=pid,
            uid=uid,
            gid=gid,
            client_address=None,
            server_address=None,
            reader=reader,
            writer=writer,
            state={
                'mode': self.mode or ConnectionType.PERSISTENT,
                'created': time.time(),
                'updated': time.time(),
                'closed': None
                }
            )