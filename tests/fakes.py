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
        self.environs = {}
        self.agents = None
        self.agents_calls = []
        self.stopped = True
        self.stop_calls = []

    def realpath(self, path):
        return self.links.get(path, path)

    def which(self, command, path):
        return self.found.get(command)

    def rss_kb(self, pid):
        return self.rss.get(pid)

    def rss_many(self, pids):
        self.rss_calls.append(list(pids))
        return {pid: self.rss[pid] for pid in pids if pid in self.rss}

    def environ(self, pid):
        return self.environs.get(pid)

    def cmdline(self, pid):
        return self.cmdlines.get(pid)

    def exe(self, pid):
        return self.exes.get(pid)

    def has_proc(self):
        return self.proc

    def claude_agents(self, command, env):
        self.agents_calls.append((command, env))
        return self.agents

    def claude_stop(self, command, short_id, env):
        self.stop_calls.append((command, short_id, env))
        return self.stopped
