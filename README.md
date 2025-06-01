# Chat Real-Time TCP-over-UDP (Go-Back-N)

Aplikasi live-chat yang mensimulasikan koneksi TCP over UDP, dengan GUI berbasis **Tkinter** dan server Python.

---

## Fitur

* **Handshake mirip TCP** (SYN, SYN-ACK, ACK) dan penutupan FIN.
* **Go-Back-N**: memecah pesan jadi blok 64 byte dan mengirimkan blok pesan secara berurutan.
* **Heartbeat** tiap 1 detik + **AFK timeout** 30 detik.
* **Suara ke teks** via PyAudio dan SpeechRecognition (kreativitas).
* Tampilan gelap **Tkinter** dengan bubble pesan dan auto-scroll.
* Perintah: `!disconnect`, `!change <nama>`, `!kill <password>`.
* Cross-platform: Windows, Linux/WSL, macOS.

---

## Cara Kerja

1. **Client - Server** dihubungkan melalui metode UDP port 42234.
2. **Handshake 3 langkah** memastikan koneksi antara client dan server terjalin meskipun di atas UDP yang _connectionless_.
3. **Server** mem-*broadcast* pesan ke semua client menggunakan paket UDP yang dipecah jadi segmen (Go-Back-N). Kalau ada segmen hilang, server tidak menunggu ACK tapi data berikutnya akan tetap terkirim. Chat masih bisa jalan dengan satu paket per pesan.
4. **Heartbeat** menjaga koneksi tetap hidup. Jika client tidak kirim heartbeat selama 30 detik, dianggap AFK dan packet didrop.

---

## Instalasi & Kebutuhan

### Kebutuhan

* **Python 3.11**
* **Tkinter** (bawaan CPython)
* `speech_recognition` (dengan nama package `SpeechRecognition`) (bonus kreativitas)
* `pyaudio` (bonus kreativitas, install di Windows melalui wheel dari GitHub)
* **Pinggy** (opsional, untuk NAT/port forwarding)

### Langkah Awal
1. Pastikan terminal sudah berada pada root direktori (tugas-besar-if2230-jaringan-komputer-dotkom/)
2. Masuk ke Folder Dotkom:
```bash
cd Dotkom
```

### Install Dependencies

```bash
pip install SpeechRecognition
pip install pyaudio
```

> **Di Windows**: kalau `pip install pyaudio` gagal, download `.whl` dari [https://github.com/dev-jam/opensesame_plugin_installer/blob/master/PyAudio-0.2.11-cp311-cp311-win_amd64.whl].

---

## Run di jaringan lokal (2 komputer dalam 1 jaringan LAN)

1. **Server**:

   ```bash
   python server.py  # mendengarkan di 0.0.0.0:42234/udp
   ```
2. **Client**:

   ```bash
   python client.py
   ```
Di GUI, masukkan:
   * *Your Name*: misal `Budi`
   * *Server IP*: alamat IP tempat server dijalankan, misal `192.168.1.42` atau `127.0.0.1` jika server dan client dijalankan di komputer yang sama.
   * *Your Port*: misal `50000` (pilih port UDP yang kosong)
   * Klik Connect

---

## Run melalui Pinggy (Port Forwarding)

### Server

1. Run script PowerShell (Windows) untuk run pinggy.exe sebagai tunnel:

   ```bash
   ./port_forwarding.ps1
   ```
   Atau jika menggunakan Linux (WSL), run perintah berikut di terminal:
   ```bash
   pinggy -p 443 -R0:127.0.0.1:42234 TE5L4FmeNFw+udp@free.pinggy.io
   ```


   Pada terminal Pinggy akan muncul tulisan seperti `rnhco-180-244-133-40.a.free.pinggy.link:41377 -> 127.0.0.1:42234` setelah koneksi tunnel berhasil. Salin URL sebelum `->`.
2. Di terminal yang berbeda, run ```python server.py``` (port 42234) seperti metode LAN.

### Client
Sama seperti metode LAN, run ```python client.py```.
Di GUI, masukkan:
   * *Your Name*: misal `Budi`
   * *Server IP*: URL pinggy.link:port yang diperoleh dari terminal pinggy, contoh: `rnhco-180-244-133-40.a.free.pinggy.link:41377`
   * *Your Port*: misal `50000` (pilih port UDP yang kosong)
   * Klik Connect



---

## Perintah client

* `!disconnect` → Keluar chat.
* `!change <namaBaru>` → Ganti nama tampilan.
* `!kill <password>` → Matikan server jika password benar.

---

## Struktur Folder

```
.  
├── client.py             # GUI Tkinter  
├── server.py             # Server UDP + logika heartbeat  
├── features/             # Kode lapisan protokol  
│   ├── better_udp_socket.py  # Handshake & utilitas socket  
│   ├── flow_control.py       # Go-Back-N sender/receiver  
│   └── segment.py            # Format header (SRC/DST/SEQ/ACK/...)
└── README.md             # Readme
```

---

## Troubleshooting

* **Pesan tidak muncul di client**:

  * Pastikan server mencetak `Sent N bytes to (ip,port)` ke terminal.
  * Buka firewall untuk mengizinkan koneksi UDP 42234.
  * Di Windows: jalankan server & client di jaringan privat atau izinkan melalui firewall.

* **Error `WinError 10013`**:

  * Artinya port 42234 sudah dipakai. Jika ada aplikasi yang menggunakan port itu, stop aplikasi tersebut atau ubah `SRC_PORT` di `server.py`.

* **Paket hilang/lag di internet**:

  * Tingkatkan `MAX_PAYLOAD_SIZE` (misal jadi 128) untuk mengurangi jumlah segmen.

* **`ModuleNotFoundError: pyaudio`**:

  * Pasang `pyaudio` dari wheel di Windows.

---

## Rencana Pengembangan

* WebSocket gateway (akses via browser).
* Enkripsi (DTLS).
* Transfer file dengan resume.
* Pindah ke `asyncio` buat skalabilitas lebih baik.

---

## License

This project is licensed under the MIT License – see the [LICENSE](LICENSE.md) file for details.