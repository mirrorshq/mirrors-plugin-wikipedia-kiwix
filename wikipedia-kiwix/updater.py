#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
import json
import time
import pysvn
import pathlib
import tempfile
import subprocess
import atomicwrites
import mirrors.plugin


class Main:

    def __init__(self):
        # parameters
        self.cfg = mirrors.plugin.params["config"]
        self.country = mirrors.plugin.params["country"]
        self.stateDir = mirrors.plugin.params["state-directory"]
        self.dataDir = mirrors.plugin.params["storage-file"]["data-directory"]

        # file location
        self.libraryFile = os.path.join(self.stateDir, "library.list")

        # download source
        self.rsyncUrl = None
        self.fileUrlList = []

    def run(self):
        while True:
            if self._getDownloadSourceLibMirror():
                break
            if self._getDownloadSourcePmdb():
                break
            self.rsyncUrl = "rsync://download.kiwix.org/download.kiwix.org/zim/wikipedia/"    # trailing slash is neccessary
            self.fileUrlList = []
            break
        while True:
            fileList = self._getFileList()
            if self._download(fileList) == 0:
                break
        self._rsync()
        self._generateLibraryListFile()

    def _getDownloadSourceLibMirror(self):
        # FIXME
        return False

    def _getDownloadSourcePmdb(self):
        print("Get download source from public-mirror-db...")
        try:
            ret = _Util.pmdbGetMirrors("kiwix", "kiwix", self.country, ["rsync"], 1)
            if len(ret) > 0:
                self.rsyncUrl = ret[0]
                self.rsyncUrl = os.path.join(self.rsyncUrl, "zim/wikipedia/")                 # trailing slash is neccessary
                self.fileUrlList = _Util.pmdbGetMirrors("kiwix", "kiwix", self.country, ["http", "https", "ftp"])
                self.fileUrlList = [os.path.join(x, "zim/wikipedia") for x in self.fileUrlList]
                print("Found:")
                print("    rsync source: %s" % (self.rsyncUrl))
                for url in self.fileUrlList:
                    print("    file source: %s" % (url))
                return True
            else:
                # no rsync source in this country, we bet there's not any source in this country
                print("No appropriate source found.")
                return False
        except Exception:
            print("Failed.")
            raise    # FIXME
            return False

    def _getFileList(self):
        print("Get file list...")

        # get file list
        fileList = []
        if True:
            cmd = ""
            cmd += "/usr/bin/rsync -rlptD --no-motd --list-only "               # we use "-rlptD" insead of "-a" so that the remote user/group is ignored
            cmd += self.__getRsyncFilterArgStr()
            cmd += " %s" % (self.rsyncUrl)
            for item in _Util.shellCall(cmd).split("\n"):
                # "drwxr-xr-x          2,380 2021/01/18 12:55:02 ./abc" -> "./abc"
                m = re.fullmatch(r'\S+ +\S+ +\S+ +\S+ +(.*)', item)
                if m is not None:
                    fileList.append(m.group(1))

        # filter file list, only keep the newst if the file likes "wikipedia_ab_all_maxi_2020-11.zim"
        # FIXME: this filter would be invalidated when rsync
        if False:
            prefixDict = dict()
            for fn in fileList:
                m = re.fullmatch("(.*)_([0-9-]+)\\.zim", fn)
                if m is None:
                    continue
                if m.group(1) not in prefixDict or prefixDict[m.group(1)] < m.group(2):
                    prefixDict[m.group(1)] = m.group(2)
            fileList2 = []
            for fn in fileList:
                m = re.fullmatch("(.*)_([0-9-]+)\\.zim", fn)
                if m is None:
                    fileList2.append(fn)
                    continue
                if m.group(2) == prefixDict[m.group(1)]:
                    fileList2.append(fn)
                    continue
            fileList = fileList2

        return fileList

    def _download(self, fileList):
        if len(self.fileUrlList) == 0:
            return 0

        count = 0
        for fn in fileList:
            if os.path.exists(os.path.join(self.dataDir, fn)):
                continue
            print("Download \"%s\"..." % (fn))
            _Util.cmdExec("/usr/bin/aria2c", "-d", self.dataDir, *[os.path.join(x, fn) for x in self.fileUrlList])
            count += 1
        return count

    def _rsync(self):
        print("Synchronize...")

        cmd = ""
        cmd += "/usr/bin/rsync -rlptD -z -v --delete-excluded --partial -H "    # we use "-rlptD" insead of "-a" so that the remote user/group is ignored
                                                                                # we don't use --delete, it's safer
        cmd += self.__getRsyncFilterArgStr()
        cmd += " %s %s" % (self.rsyncUrl, self.dataDir)
        _Util.shellExec(cmd)

    def _generateLibraryListFile(self):
        # get latest files
        latestFileList = None
        if True:
            latestFileDict = dict()         # <prefix:time>
            for fn in os.listdir(self.dataDir):
                m = re.fullmatch("(.*)_([0-9-]+)\\.zim")
                if m is None:
                    continue
                if m.group(1) in latestFileDict and latestFileDict[m.group(1)] < m.group(2):
                    latestFileDict[m.group(1)] = m.group(2)
            latestFileList = ["%s_%s.zim" % (k, v) for k, v in latestFileDict.items()]
            latestFileList.sort()

        # generate new library.list
        with atomicwrites.atomic_write(self.libraryFile, overwrite=True) as f:
            for fn in latestFileList:
                f.write(fn + "\n")

    def __getRsyncFilterArgStr(self):
        allFileTypes = ["maxi", "mini", "nopic"]

        # "file-type" in config:
        #   wikipedia_ab_all_maxi_2020-11.zim, wikipedia_ab_all_mini_2019-02.zim, wikipedia_ab_all_nopic_2020-11.zim
        #                    ^^^^                               ^^^^                               ^^^^^
        fileType = "*"
        if "file-type" in self.cfg:
            if self.cfg["file-type"] not in ["*"] + allFileTypes:
                raise Exception("invalid \"file-type\" in config")

        # "include-lang", "exclude-lang" in config:
        #   wikipedia_ab_all_maxi_2020-11.zim
        #             ^^
        langIncList = []
        langExcList = []
        if "include-lang" in self.cfg:
            langIncList = self.cfg["include-lang"]
        if "exclude-lang" in self.cfg:
            langExcList = self.cfg["exclude-lang"]
        if len(langIncList) > 0 and len(langExcList) > 0:
            raise Exception("\"include-lang\" and \"exclude-lang\" can not co-exist in config")

        argStr = " "
        for la in langExcList:
            argStr += "-f '- wikipedia_%s_*.zim' " % (la)                                  # ignore "exclude-lang"
        if fileType != "*":
            for ft in allFileTypes:
                argStr += "-f '- wikipedia_*_*_%s_*.zim' " % (ft)                          # ignore "file-type"
        if len(langIncList) > 0:
            for la in langIncList:
                argStr += "-f '+ wikipedia_%s_all_*.zim' " % (la)                          # we only download "_all_" category files
        else:
            argStr += "-f '+ wikipedia_*_all_*.zim' "                                      # we only download "_all_" category files
        argStr += "-f '- *' "
        return argStr


class _Util:

    @staticmethod
    def pmdbGetMirrors(name, typeName, countryCode, protocolList, count=None):
        buf = _Util.githubGetFileContent("mirrorshq", "public-mirror-db", os.path.join(name, typeName + ".json"))
        jsonList = json.loads(buf)

        # filter by protocolList
        jsonList = [x for x in jsonList if x["protocol"] in protocolList]

        # filter by countryCode
        jsonList = [x for x in jsonList if x["country-code"] == countryCode]

        # filter by count
        if count is not None:
            jsonList = jsonList[0:min(len(jsonList), count)]

        # return value
        return [x["url"] for x in jsonList]

    @staticmethod
    def githubGetFileContent(user, repo, filepath):
        url = "https://github.com/%s/%s/trunk/%s" % (user, repo, filepath)
        with _TempCreateFile() as tmpFile:
            pysvn.Client().export(url, tmpFile, force=True)
            return pathlib.Path(tmpFile).read_text()

    @staticmethod
    def cmdCall(cmd, *kargs):
        # call command to execute backstage job
        #
        # scenario 1, process group receives SIGTERM, SIGINT and SIGHUP:
        #   * callee must auto-terminate, and cause no side-effect
        #   * caller must be terminated by signal, not by detecting child-process failure
        # scenario 2, caller receives SIGTERM, SIGINT, SIGHUP:
        #   * caller is terminated by signal, and NOT notify callee
        #   * callee must auto-terminate, and cause no side-effect, after caller is terminated
        # scenario 3, callee receives SIGTERM, SIGINT, SIGHUP:
        #   * caller detects child-process failure and do appopriate treatment

        ret = subprocess.run([cmd] + list(kargs),
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             universal_newlines=True)
        if ret.returncode > 128:
            # for scenario 1, caller's signal handler has the oppotunity to get executed during sleep
            time.sleep(1.0)
        if ret.returncode != 0:
            print(ret.stdout)
            ret.check_returncode()
        return ret.stdout.rstrip()

    @staticmethod
    def shellCall(cmd):
        # call command with shell to execute backstage job
        # scenarios are the same as _Util.cmdCall

        ret = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             shell=True, universal_newlines=True)
        if ret.returncode > 128:
            # for scenario 1, caller's signal handler has the oppotunity to get executed during sleep
            time.sleep(1.0)
        if ret.returncode != 0:
            print(ret.stdout)
            ret.check_returncode()
        return ret.stdout.rstrip()

    @staticmethod
    def cmdExec(cmd, *kargs):
        # call command to execute frontend job
        #
        # scenario 1, process group receives SIGTERM, SIGINT and SIGHUP:
        #   * callee must auto-terminate, and cause no side-effect
        #   * caller must be terminate AFTER child-process, and do neccessary finalization
        #   * termination information should be printed by callee, not caller
        # scenario 2, caller receives SIGTERM, SIGINT, SIGHUP:
        #   * caller should terminate callee, wait callee to stop, do neccessary finalization, print termination information, and be terminated by signal
        #   * callee does not need to treat this scenario specially
        # scenario 3, callee receives SIGTERM, SIGINT, SIGHUP:
        #   * caller detects child-process failure and do appopriate treatment
        #   * callee should print termination information

        # FIXME, the above condition is not met, FmUtil.shellExec has the same problem

        ret = subprocess.run([cmd] + list(kargs), universal_newlines=True)
        if ret.returncode > 128:
            time.sleep(1.0)
        ret.check_returncode()

    @staticmethod
    def shellExec(cmd):
        ret = subprocess.run(cmd, shell=True, universal_newlines=True)
        if ret.returncode > 128:
            time.sleep(1.0)
        ret.check_returncode()


class _TempCreateFile:

    def __init__(self, dir=None):
        f, self._fn = tempfile.mkstemp(dir=dir)
        os.close(f)

    def __enter__(self):
        return self._fn

    def __exit__(self, type, value, traceback):
        os.unlink(self._fn)


###############################################################################

if __name__ == "__main__":
    Main().run()
