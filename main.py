import requests, subprocess, os, stat, time, shutil
# The EULA for the prebuild rcc is hard to understand, so here is a free version under Apache-2.0 license
local_filename = "rcc"
# If testing toward app.openiap.io you MUST update this wiq to your own workitem queue
defaultwiq = "rcctest"
if(not os.path.exists(local_filename)):
    url = 'https://github.com/skadefro/rcc-build/raw/master/build/linux64/rcc'
    totalbits = 0
    response = requests.get(url)
    if response.status_code == 200:
        with open(local_filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    totalbits += 1024
                    print("Downloaded",totalbits*1025,"KB...")
                    f.write(chunk)
st = os.stat(local_filename)
os.chmod(local_filename, st.st_mode | stat.S_IEXEC)

import asyncio, os, openiap, traceback, zlib, json, logging
import robot
class Worker:
    async def __ProcessWorkitem(self, workitem, payload):
        logging.info(f"Processing workitem id {workitem._id} retry #{workitem.retries}")
        if("url" in payload):
            os.environ["url"] = payload["url"]

        command = [f"{os.getcwd()}/rcc", "run"]
        subprocess.run(command)
        # command = 'python -m robot --report NONE --outputdir output --logtitle "Task Log" --variable FAIL:True -t "Execute Google image search and store the first result image" tasks.robot'
        # process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        workitem.name = f"Robot example completed"
        return payload
    async def __ProcessWorkitemWrapper(self, workitem):
        if(os.path.exists("./output")):
            shutil.rmtree("./output")
        try:
            for f in workitem.files:
                if (f.file and len(f.file) > 0):
                    if f.compressed:
                        with open(f.filename, "wb") as out_file:
                            out_file.write(zlib.decompress(f.file))
                    else:
                        with open(f.filename, "wb") as out_file:
                            out_file.write(f.file)
                else:
                    result = await self.c.DownloadFile(Id=f._id)
            payload = json.loads(workitem.payload)
            payload = await self.__ProcessWorkitem(workitem, payload)
            workitem.payload = json.dumps(payload)
            workitem.state = "successful"
            _files = []
            if(os.path.exists("./output")):
                files = os.listdir("output")
                for file in files:
                    if(os.path.isfile("output/" + file)):
                        print(f"uploading output/{file}")
                        _files.append("output/" + file)
            await self.c.UpdateWorkitem(workitem, _files, True)
        except (Exception,BaseException) as e:
            workitem.state = "retry"
            workitem.errortype = "application" # business rule will never retry / application will retry as mamy times as defined on the workitem queue
            workitem.errormessage = "".join(traceback.format_exception_only(type(e), e)).strip()
            workitem.errorsource = "".join(traceback.format_exception(e))
            await self.c.UpdateWorkitem(workitem)
            print(repr(e))
            traceback.print_tb(e.__traceback__)
        if(os.path.exists("./output")):
            shutil.rmtree("./output")
    async def __loop_workitems(self):
        counter = 1
        workitem = await self.c.PopWorkitem(self.wiq)
        while workitem != None:
            counter = counter + 1
            await self.__ProcessWorkitemWrapper(workitem)
            workitem = await self.c.PopWorkitem(self.wiq)
        if(counter > 0):
            logging.info(f"No more workitems in {self.wiq} workitem queue")
    async def __wait_for_message(self, client, message, payload):
        asyncio.run_coroutine_threadsafe(self.__loop_workitems(), client.loop)
        # await self.__loop_workitems()
    async def onconnected(self, client):
        await client.Signin()
        if(self.queue != ""):
            queuename = await self.c.RegisterQueue(self.queue, self.__wait_for_message)
            print(f"Consuming queue {queuename}")
    async def main(self):
        self.queue = os.environ.get("queue", "")
        self.wiq = os.environ.get("wiq", "")
        if(self.wiq == ""): self.wiq = defaultwiq
        self.c = openiap.Client()
        self.c.onconnected = self.onconnected
        if(self.queue == ""): self.queue = self.wiq
        if(self.queue == ""):
            await self.c.Signin()
            while True:
                await self.__loop_workitems()
                await asyncio.sleep(30) 
                # time.sleep(30)
        else:
            while True:
                # time.sleep(1)
                await asyncio.sleep(1) 
if __name__ == '__main__':
    loglevel = os.environ.get("loglevel", logging.INFO)
    if loglevel==logging.INFO:
        logging.basicConfig(format="%(message)s", level=loglevel)
    else:
        logging.basicConfig(format="%(levelname)s:%(message)s", level=loglevel)
    wiq = os.environ.get("wiq", "")
    if(wiq == ""): wiq = defaultwiq
    if(wiq == ""): raise ValueError("Workitem queue name (wiq) is required")
    w = Worker()
    asyncio.run(w.main())
