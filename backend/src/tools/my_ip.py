from src.tools.cli import CLIControl


class MyIp:

    def __init__(self):
        self.cli = CLIControl()

    @property
    def public(self):
        result = self.cli.execute(
            ["dig", "+short", "myip.opendns.com", "@resolver1.opendns.com"],
            return_proc=True,
        )
        if result.returncode != 0:
            return None
        return result.stdout

    @property
    def private(self):
        result = self.cli.execute(
            "echo $(hostname -I | awk '{print $1}')",
            return_proc=True,
            is_text=True,
            shell=True,
        )
        if result.returncode != 0:
            return None
        return result.stdout


if __name__ == "__main__":
    my_ip = MyIp()
    print(my_ip.public)
    print(my_ip.private)
