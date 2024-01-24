ELVA client -(ELVA API)- ELVA service -- Y-CRDT provider -|- (ELVA server) -- ELVA peer

# ELVA Client
- in foreground as websocket client
- display current status (connection, rooms, dir, peers etc.)
- send commands to ELVA service over ELVA API 
- can be: CLI, TUI, GUI, (website)

# ELVA Service
- in background as websocket server (or web server)
- receives commands by ELVA client over ELVA API and processes them
- sends back response to ELVA client
- handles rooms
- syncs project status with connected peers/servers
- opens room upon request
- authenticates messages

## Room Handling
- class RoomHandler, class Room, class TunnelRoom(Room), class YRoom(Room)
- room == project root dir or project file
- authentication checking
- file I/O
  - read from disk and send to provider or
  - receive from provider and write to disk
- Y-CRDT processing
  - generate updates and send to provider or
  - receive updates from provider and apply

# Y-CRDT Provider
- ypy-websocket, (ypy-webrtc), (ypy-holepunch)
- sends sync messages to peers
- receives sync messages from peers and forwards them to ELVA service

# ELVA Server (aka Broadcasting Peer)
- a message broker
- broadcasts incoming messages to all other peers

# ELVA Robot Service (aka receive-only peer)
- like regular service, except it does not send any messages (only receives)
