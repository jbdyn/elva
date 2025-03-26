import cmd
import io
import os
from queue import Queue

from textual import log
from textual.app import App
from textual.reactive import reactive
from textual.widget import Widget


class ELVAREPL(cmd.Cmd):
    intro = "This is ELVA"
    prompt = "elva > "

    def precmd(self, line):
        # if line == "EOF":
        #    print()
        #    exit()
        return line

    def cmdloop(self, intro=None):
        """Repeatedly issue a prompt, accept input, parse an initial prefix
        off the received input, and dispatch to action methods, passing them
        the remainder of the line as argument.

        """

        self.preloop()
        if self.use_rawinput and self.completekey:
            try:
                import readline

                self.old_completer = readline.get_completer()
                readline.set_completer(self.complete)
                if True:
                    if self.completekey == "tab":
                        # libedit uses "^I" instead of "tab"
                        command_string = "bind ^I rl_complete"
                    else:
                        command_string = f"bind {self.completekey} rl_complete"
                else:
                    command_string = f"{self.completekey}: complete"
                readline.parse_and_bind(command_string)
            except ImportError:
                pass
        try:
            if intro is not None:
                self.intro = intro
            if self.intro:
                self.stdout.write(str(self.intro) + "\n")
            stop = None
            while not stop:
                if self.cmdqueue:
                    line = self.cmdqueue.pop(0)
                else:
                    if self.use_rawinput:
                        try:
                            line = input(self.prompt)
                        except EOFError:
                            line = "EOF"
                        except KeyboardInterrupt:
                            print()
                            line = ""
                    else:
                        self.stdout.write(self.prompt)
                        self.stdout.flush()
                        try:
                            line = self.stdin.readline()
                        except KeyboardInterrupt:
                            print()
                            line = "\n"
                        if not len(line):
                            line = "EOF"
                        else:
                            line = line.rstrip("\r\n")
                line = self.precmd(line)
                stop = self.onecmd(line)
                stop = self.postcmd(stop, line)
            self.postloop()
        except Exception as exc:
            print(exc)
        finally:
            if self.use_rawinput and self.completekey:
                try:
                    import readline

                    readline.set_completer(self.old_completer)
                except ImportError:
                    pass

    def emptyline(self):
        pass

    def postcmd(self, stop, line):
        if line == "EOF":
            stop = True

        return stop


class REPLWidget(Widget, can_focus=True):
    content = reactive("")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.term_rfd, self.repl_wfd = os.pipe()
        self.repl_rfd, self.term_wfd = os.pipe()

        self.queue = Queue()

    def render(self):
        return self.content

    def run(self):
        with (
            open(self.repl_rfd, "rb") as raw_repl_rfile,
            io.TextIOWrapper(raw_repl_rfile) as repl_rfile,
            open(self.repl_wfd, "wb") as raw_repl_wfile,
            io.TextIOWrapper(raw_repl_wfile) as repl_wfile,
        ):
            repl = ELVAREPL(stdin=repl_rfile, stdout=repl_wfile)
            repl.use_rawinput = False
            repl.cmdloop()
            log("LOOP FINISHED")

    def read_repl(self):
        with open(self.term_rfd, "r") as term_rfile:
            while True:
                char = term_rfile.read(1)
                log("READ", char)
                self.content += char

    def write_repl(self):
        with open(self.term_wfd, "w") as term_wfile:
            while True:
                char = self.queue.get()
                term_wfile.write(char)
                term_wfile.flush()
                log("WROTE", char)

    def on_key(self, event):
        log("KEY", event.key)
        char = event.character
        if char == "\r":
            char = "\r\n"
        self.queue.put(char)
        self.content += char
        log("CONTENT", self.content)

    def on_mount(self):
        self.run_worker(self.run, thread=True)
        self.run_worker(self.read_repl, thread=True)
        self.run_worker(self.write_repl, thread=True)


class REPLApp(App):
    CSS = """
    REPLWidget {
        background: red;
    }
    """

    def compose(self):
        yield REPLWidget()

    def on_mount(self):
        self.query_one(REPLWidget).focus()


if __name__ == "__main__":
    app = REPLApp()
    app.run()
