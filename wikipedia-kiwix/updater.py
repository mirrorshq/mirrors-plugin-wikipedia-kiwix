#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
import time
import subprocess
import atomicwrites
import mirrors.plugin


class Main:

    def __init__(self):
        self.cfg = mirrors.plugin.params["config"]
        self.stateDir = mirrors.plugin.params["state-directory"]
        self.dataDir = mirrors.plugin.params["storage-file"]["data-directory"]
        self.libraryFile = os.path.join(self.stateDir, "library.list")

    def run(self):
        self._download()
        self._generateLibraryListFile()

    def _download(self):
        rsyncSource = "rsync://download.kiwix.org/download.kiwix.org/zim/wikipedia/"    # trailing slash is neccessary

        cmd = ""
        cmd += "/usr/bin/rsync -rlptD -z -v --delete --delete-excluded --partial -H "   # we use "-rlptD" insead of "-a" so that the remote user/group is ignored
        cmd += self.__getRsyncFilterArgStr()
        cmd += " %s %s" % (rsyncSource, self.dataDir)
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

        # "latest-only" in config:
        # FIXME: there's no simple way to implment this flag because different zim file has different latest time
        if "latest-only" in self.cfg:
            raise Exception("\"latest-only\" in config is not implemented yet")

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
    def shellExec(cmd):
        ret = subprocess.run(cmd, shell=True, universal_newlines=True)
        if ret.returncode > 128:
            time.sleep(1.0)
        ret.check_returncode()


###############################################################################

if __name__ == "__main__":
    Main().run()
