import anyio
import random
import time
import queue

def connect(connected):
    print("? connecting to server...")
    time.sleep(10)
    print("! connection established")
    anyio.from_thread.run_sync(connected.set)

def send(q):
    while True:
        file = q.get()
        print("> |  syncing file", file)
        time.sleep(random.randint(2, 5))
        print("> |- finished syncing file", file)
  

async def sync(connected, q):
    await connected.wait()
    await anyio.to_thread.run_sync(send, q)


async def detect(q):
    i = 0
    while True:
        print("> event for file", str(i), "detected")
        q.put(str(i))
        await anyio.sleep(random.randint(1, 1))
        i += 1

async def aconnect(connected):
    await anyio.to_thread.run_sync(connect, connected)

async def main():
    connected = anyio.Event()
    q = queue.Queue()
    async with anyio.create_task_group() as tg:
        tg.start_soon(aconnect, connected)
        tg.start_soon(detect, q)
        tg.start_soon(sync, connected, q)

anyio.run(main)        
