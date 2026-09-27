"""Stand-ins for the plugin's outside world, shared by the tests."""


class FakeSystem:
    def __init__(self, cmdlines=None, exes=None, proc=True):
        self.cmdlines = cmdlines or {}
        self.exes = exes or {}
        self.proc = proc
        self.rss = {}
        self.links = {}
        self.found = {}
        self.rss_calls = []

    def realpath(self, path):
        return self.links.get(path, path)

    def which(self, command, path):
        return self.found.get(command)

    def rss_kb(self, pid):
        return self.rss.get(pid)

    def rss_many(self, pids):
        self.rss_calls.append(list(pids))
        return {pid: self.rss[pid] for pid in pids if pid in self.rss}

    def cmdline(self, pid):
        return self.cmdlines.get(pid)

    def exe(self, pid):
        return self.exes.get(pid)

    def has_proc(self):
        return self.proc
