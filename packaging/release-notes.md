## Download

| File | Runs on | What you get |
| --- | --- | --- |
| **`osu-coach-{version}-setup.exe`** | Windows 10 / 11 | **Recommended.** Installs for your user (no admin rights), adds a Start menu and optional desktop shortcut and opens osu! coach in your browser. To update, install a newer one over it: your settings, replay cache and progress are kept. |
| `osu-coach-{version}-x64.msi` | Windows 10 / 11 | The desktop app: osu! coach in its own window. Installs for all users (asks for admin rights); also for silent installs, `msiexec /i osu-coach-{version}-x64.msi /qn`. |
| `osu-coach-{version}-windows-portable.zip` | Windows 10 / 11 | The desktop app without installing it: unzip the folder anywhere (also a USB stick) and start `osu! coach.exe` in it. |
| `osu-coach_{version}_amd64.deb` | Ubuntu 22.04+, Debian 12+, Linux Mint 21+ (64-bit) | The desktop app in its own window. Install with `sudo apt install ./osu-coach_{version}_amd64.deb`, then start **osu! coach** from the app menu. Remove it with `sudo apt remove osu-coach`. |

The installers are not code-signed yet, so Windows SmartScreen may say *Windows protected your PC*: choose
**More info → Run anyway**. `SHA256SUMS.txt` lists the checksum of every file (`sha256sum -c SHA256SUMS.txt
--ignore-missing` on Linux, `Get-FileHash <file>` in PowerShell).
None of them needs Python or Node.js.

## Open source

osu! coach is free and open source under the [MIT license](https://github.com/DeMotione/osu-coach/blob/v{version}/LICENSE).
The source code of this version is attached below (**Source code**, zip / tar.gz). To run it from source on
Windows, Linux or macOS (Python 3.11+, and Node.js 22.12+ to build the web app once):

```
git clone --branch v{version} https://github.com/DeMotione/osu-coach.git
cd osu-coach
./run.sh            # Windows: run.bat
```

The first run sets everything up and opens the app at http://localhost:8501. How to build the installers yourself
is in the [README](https://github.com/DeMotione/osu-coach/blob/v{version}/README.md) and
[desktop/README.md](https://github.com/DeMotione/osu-coach/blob/v{version}/desktop/README.md). Bug reports,
ideas and pull requests are welcome.
