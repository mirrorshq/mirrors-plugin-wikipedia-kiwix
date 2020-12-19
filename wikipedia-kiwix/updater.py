#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
import sys
import time
import json
import subprocess
import atomicwrites


def main():
    cfg = json.loads(sys.argv[1])["config"]
    stateDir = json.loads(sys.argv[1])["state-directory"]
    dataDir = json.loads(sys.argv[1])["storage-file"]["data-directory"]

    # download
    _download(cfg, dataDir)

    # generate library.list
    libraryFile = os.path.join(stateDir, "library.list")
    _generateLibraryListFile(dataDir, libraryFile)


def _download(cfg, dataDir):
    allFileTypes = ["maxi", "mini", "nopic"]
    rsyncSource = "rsync://download.kiwix.org/zim/wikipedia"

    # "file-type" in config:
    #   wikipedia_ab_all_maxi_2020-11.zim, wikipedia_ab_all_mini_2019-02.zim, wikipedia_ab_all_nopic_2020-11.zim
    #                    ^^^^                               ^^^^                               ^^^^^
    fileType = "*"
    if "file-type" in cfg:
        if cfg["file-type"] not in ["*"] + allFileTypes:
            raise Exception("invalid \"file-type\" in config")

    # "include-lang", "exclude-lang" in config:
    #   wikipedia_ab_all_maxi_2020-11.zim
    #             ^^
    langIncList = []
    langExcList = []
    if "include-lang" in cfg:
        langIncList = cfg["include-lang"]
    if "exclude-lang" in cfg:
        langExcList = cfg["exclude-lang"]
    if len(langIncList) > 0 and len(langExcList) > 0:
        raise Exception("\"include-lang\" and \"exclude-lang\" can not co-exist in config")

    # "latest-only" in config:
    # FIXME: there's no simple way to implment this flag because different zim file has different latest time
    if "latest-only" in cfg:
        raise Exception("\"latest-only\" in config is not implemented yet")

    # execute
    cmd = ""
    cmd += "/usr/bin/rsync -rlptD -z -v --delete --delete-excluded --partial -H "   # we use "-rlptD" insead of "-a" so that the remote user/group is ignored
    for la in langExcList:
        cmd += "-f '- wikipedia_%s_*.zim' " % (la)                                  # ignore "exclude-lang"
    if fileType != "*":
        for ft in allFileTypes:
            cmd += "-f '- wikipedia_*_*_%s_*.zim' " % (ft)                          # ignore "file-type"
    if len(langIncList) > 0:
        for la in langIncList:
            cmd += "-f '+ wikipedia_%s_all_*.zim' " % (la)                          # we only download "_all_" category files
    else:
        cmd += "-f '+ wikipedia_*_all_*.zim' "                                      # we only download "_all_" category files
    cmd += "-f '- *' "
    cmd += "%s %s" % (rsyncSource, dataDir)
    _Util.shellExec(cmd)


def _generateLibraryListFile(dataDir, libraryFile):
    # get latest files
    latestFileList = None
    if True:
        latestFileDict = dict()         # <prefix:time>
        for fn in os.listdir(dataDir):
            m = re.fullmatch("(.*)_([0-9-]+)\\.zim")
            if m is None:
                continue
            if m.group(1) in latestFileDict and latestFileDict[m.group(1)] < m.group(2):
                latestFileDict[m.group(1)] = m.group(2)
        latestFileList = ["%s_%s.zim" % (k, v) for k, v in latestFileDict.items()]
        latestFileList.sort()

    # generate new library.list
    with atomicwrites.atomic_write(libraryFile, overwrite=True) as f:
        for fn in latestFileList:
            f.write(fn + "\n")


class _Util:

    @staticmethod
    def shellExec(cmd):
        ret = subprocess.run(cmd, shell=True, universal_newlines=True)
        if ret.returncode > 128:
            time.sleep(1.0)
        ret.check_returncode()


###############################################################################

if __name__ == "__main__":
    main()
