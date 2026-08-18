📡 Local Share

Move files between your laptop and phone in seconds — no cloud, no USB cable, no account.

I built Local Share because I got tired of uploading files to cloud storage just to transfer something from my laptop to my phone. If both devices are on the same Wi-Fi network, they should just talk to each other.

That's exactly what this project does.

It runs a small web server on your computer, and any device connected to the same network can instantly access it from a browser. Your files stay on your own network and never pass through someone else's servers.

---

What it can do

- Drag and drop files to upload
- See upload progress in real time
- Preview images and videos without downloading them
- Search files instantly
- Rename files directly in the browser
- Connect by scanning a QR code
- Auto-discover the server using mDNS or UDP discovery
- Password-protected login
- Files are encrypted while stored on disk
- Live chat between connected devices
- Shows who is online
- Dark mode
- Can be packaged into a single Windows ".exe" so Python isn't required

If you occasionally need to share a file with someone outside your Wi-Fi, there's also an optional Cloudflare Tunnel integration that creates a temporary HTTPS link without opening ports or creating an account.

---

Why I made this

There are already lots of file-sharing apps, but most of them depend on cloud storage, ads, accounts, or internet access.

Sometimes I just want to send a PDF, photo, or video from my laptop to my phone while sitting on the same Wi-Fi.

That should take a few seconds—not three different apps.

So I made Local Share.

---

Getting started

git clone https://github.com/kiran99756/Localshare.git
cd Localshare
pip install -r requirements.txt
python main.py

When the server starts, it prints the local URL and generates a password.

Open the URL on your phone or simply scan the QR code shown on the page.

That's it.

---

Windows

If you don't want to install Python, download the ready-to-use "LocalShare.exe" from the Releases page and double-click it.

No setup required.

---

Tech Stack

- FastAPI
- WebSockets
- SQLite
- Vanilla JavaScript
- HTML & CSS
- Cryptography (Fernet encryption)
- Zeroconf (mDNS)
- PyInstaller

No frontend framework. No build process. Just simple technologies that work.

---

Future plans

There are still plenty of ideas I'd like to add.

- Native Android app
- Linux and macOS builds
- Folder uploads
- ZIP uploads
- Auto-delete after a chosen time
- Better mobile experience
- Faster transfers for large files

---

Contributing

If you find a bug, have an idea, or want to improve something, feel free to open an issue or submit a pull request.

Even small improvements are welcome.

---

License

MIT License.