import sys
import asyncio
from bleak import BleakClient
from bleakheart import HeartRate

async def run_ble_client(device, hr_callback):

    def keyboard_handler(loop=None):
        input() # clear input buffer
        print (f"Quitting on user command")
        if loop==None:
            quitclient.set()
        else:
            loop.call_soon_threadsafe(quitclient.set)

    def disconnected_callback(client):
        print("Sensor disconnected")
        quitclient.set()

    quitclient=asyncio.Event()
    async with BleakClient(device, disconnected_callback=
                           disconnected_callback) as client:
        print(f"Connected: {client.is_connected}")
        loop=asyncio.get_running_loop()
        loop.add_reader(sys.stdin, keyboard_handler)
        print(">>> Hit Enter to exit <<<")
        heartrate=HeartRate(client, callback=hr_callback,
                            instant_rate=True,
                            unpack=True)
        await heartrate.start_notify()
        await quitclient.wait()
        if client.is_connected:
            await heartrate.stop_notify()
        loop.remove_reader(sys.stdin)