'''
This module defines the base IPC server. 
Subclass from this class to create a custom IPC server implementation.
@author: Thomas Wanderer
'''

try:
    # Imports
    import asyncio
    import time
    from typing import TypeVar, Optional, Type, Union, Iterable
    
    # free.dm Imports
    from freedm.utils.async import BlockingContextManager
    from freedm.utils import logging
    from freedm.utils.async import getLoop
    from freedm.utils.types import TypeChecker as checker
    from freedm.utils.ipc.message import Message
    from freedm.utils.ipc.protocol import Protocol
    from freedm.utils.ipc.connection import Connection, ConnectionType
    from freedm.utils.ipc.exceptions import freedmIPCMessageReader, freedmIPCMessageHandler, freedmIPCMessageWriter, freedmIPCMessageLimitOverrun
except ImportError as e:
    from freedm.utils.exceptions import freedmModuleImport
    raise freedmModuleImport(e)


IC = TypeVar('IC', bound='IPCSocketClient')


class IPCSocketClient(BlockingContextManager):
    '''
    A generic client implementation to connect to IPC servers. It can be used 
    as a contextmanager or as asyncio awaitable. It supports basic message 
    exchange and can be configured with a protocol for advanced IPC communication.
    A client can:
    - Establish ephemeral and persistent (long-living) connections
    - Read data at once or in chunks
    '''
    
    # The context (This connection)
    _connection: Connection=None
    
    # Handler coroutine
    _handler: asyncio.coroutine=None
    
    def __init__(
            self,
            loop: Optional[Type[asyncio.AbstractEventLoop]]=None,
            timeout: int=None,
            limit: Optional[int]=None,
            chunksize: Optional[int]=None,
            mode: Optional[ConnectionType]=None,
            protocol: Optional[Protocol] = None
            ) -> None:
        
        self.logger     = logging.getLogger()
        self.loop       = loop or getLoop()
        self.timeout    = timeout
        self.limit      = limit
        self.chunksize  = chunksize
        self.mode       = mode
        self.protocol   = protocol
        
    async def __aenter__(self) -> IC:
        '''
        A template function that should be implemented by any subclass
        '''
        # Call parent (Required to profit from SaveContextManager)
        await super().__aenter__()
        
        # Call pre-connection preparation
        connection = await self._init_connect()
        
        # Connect
        if connection: self._onConnectionEstablished(connection)

        # Call post-connection preparation
        if connection: await self._post_connect(connection)

        # Check & Return self
        if not connection: self.logger('IPC connection could not be established')
        return self
        
    async def __aexit__(self, *args) -> None:
        '''
        Cancel the connection handler and close the connection
        '''
        if not self.connected(): return
        
        print('CLOSING NOW via __AEXIT__!!!!')
        
        # Set internals to None again
        handler = self._handler
        connection = self._connection
        self._handler = None
        self._connection = None
             
        # Call pre-shutdown procedure
        await self._pre_disconnect(connection)
        
        # Cancel the handler  
        if handler: handler.cancel()
            
        # Close the connection
        if connection: await self.closeConnection(connection)
            
        # Call post shutdown procedure
        await self._post_disconnect(connection)

        # Call parent (Required to profit from SaveContextManager)
        await super().__aexit__(*args)

    async def __await__(self) -> IC:
        '''
        Makes this class awaitable
        '''
        return await self.__aenter__()
    
    def connected(self):
        '''
        Checks if the connection is still alive
        '''
    
        return (self._connection and not self._connection.state['closed'])
    
    def _assembleConnection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> Connection:
        '''
        Assemble a connection object based on the info we get from the reader/writer
        '''
        return Connection(
            socket=writer.get_extra_info('socket'),
            pid=None,
            uid=None,
            gid=None,
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
        
    async def closeConnection(self, connection):
        '''
        End and close an existing connection:
        Acknowledge or inform client about EOF, then close
        '''
        if not connection.writer.transport.is_closing():
            print('CLOSING CONNECTION!!!')
            try:
                if connection.reader.at_eof():
                    self.logger.debug('IPC connection closed by server')
                    connection.reader.feed_eof()
                else:
                    self.logger.debug('IPC connection closed by client')
                    if connection.writer.can_write_eof(): connection.writer.write_eof()
                await asyncio.sleep(.1)
                connection.writer.close()
            except:
                pass
            finally:
                connection.state['closed'] = time.time()
                self.logger.debug('IPC connection writer closed')
                
    def _onConnectionEstablished(self, connection: Connection) -> None:
        '''
        This function stores the connection and initializes a handler for it
        '''
        # Set connection and start the handler task
        self._connection = connection
        
        # Start the connection handler
        try:
            if not self.timeout:
                self._handler = asyncio.ensure_future(
                    self._handleConnection(self._connection), loop=self.loop
                    )
            else:
                self._handler = asyncio.ensure_future(
                    asyncio.wait_for(
                        self._handleConnection(self._connection), self.timeout, loop=self.loop
                        )
                )
        except Exception as e:
            self.logger.debug('IPC connection handler could not be initialized')
    
    async def _init_connect(self) -> Optional[Connection]:
        '''
        Template function for initializing a connection.
        It should return a connection object.
        '''
        return
    
    async def _post_connect(self, connection: Connection) -> None:
        '''
        Template function called after the establishment of a connection
        '''
        return
    
    async def _pre_disconnect(self, connection: Connection) -> None:
        '''
        Template function to prepare the closing of the connection
        before we cancel the connection handler
        '''
        return
    
    async def _post_disconnect(self, connection: Connection) -> None:
        '''
        Template function to cleanup after the connection closing was
        signaled via self.closeConnection
        '''
        return
    
    async def _handleConnection(self, connection: Connection) -> None:
        '''
        Handle the connection and listen for incoming messages until we receive an EOF.
        '''
        print('>>> STARTING CONNECTION HANDLER')
        
        # Read data depending on the connection type and handle it
        chunks = 0
        while not connection.reader.at_eof():
            # Update the connection
            connection.state['updated'] = time.time()
            # Read up to the limit or as many chunks until the limit
            try:
                if self.chunksize:
                    if self.limit and self.limit - chunks * self.chunksize < self.chunksize:
                        break
                    raw = await connection.reader.read(self.chunksize)
                    chunks += 1
                else:
                    raw = await connection.reader.read(self.limit or -1)
            except asyncio.CancelledError:
                print('<<< I, THE HANDLER GOT CANCELED !!!')
                break
            except ConnectionResetError as e:
                print('<<< I, THE CONNECTION GOT RESET !!!')
                break
            except Exception as e:
                print('HANDLER ERROR', type(e), e)
                # TODO: Don't raise an error or self.closeConnection
                #raise freedmIPCMessageReader(e)
                break
            # Handle the received message or message fragment
            if not len(raw) == 0:
                message = Message(
                    data=raw,
                    sender=connection
                    )
                try:
                    await self.handleMessage(message)
                except Exception as e:
                    # TODO: Don't raise an error or self.close
                    # await self.close()
                    raise freedmIPCMessageHandler(e)
        
        # Close this connection again
        await self.close()
    
    async def handleMessage(self, message: Message):
        '''
        A template function that should be overwritten by any subclass if required
        '''
        self.logger.debug(f'IPC client received: {message.data.decode()}')
        #await self.sendMessage('PONG' if message.data.decode() == 'PING' else message.data.decode(), message.sender)          
#         
#         SOlLEN BEI WITH ASYNC gleich Connection auf Ephemeral gesetzt werden?
#          
#         Einen Incoming Listener implementieren
#         
#         Send message implementieren

    async def sendMessage(self, message: Union[str, int, float]) -> bool:
        '''
        Send a message to either one or more connections
        '''
        
        # TODO. Es gibt ja nur eine Connection zum senden, anders als beim SERVER
        
        # TODO: Should we also cancel active sendMessage coroutines?
        
        pass
        
#         for c in [[connection] if not checker.isIterable(connection) else connection]:
#             # Write message to socket if size is met and connection not closed
#             try:
#                 message = str(message).encode()
#                 if len(message) == 0:
#                     return
#                 if self.limit and len(message) > self.limit:
#                     raise freedmIPCMessageLimitOverrun()
#                 if not c.writer.transport.is_closing():
#                     c.writer.write(message)
#                     await c.writer.drain()
#             except Exception as e:
#                 raise freedmIPCMessageWriter(e)
#             
            
        # TODO: Macht Ephemeral hier eigentlich Sinn oder nicht?
        
        # In case this is an ephemeral connection, close it immediately after sending this message
#         if c.state['mode'] == ConnectionType.EPHEMERAL:
#             await self.close()
    
    async def close(self) -> None:
        '''
        Stop this client connection
        '''
        await self.__aexit__()