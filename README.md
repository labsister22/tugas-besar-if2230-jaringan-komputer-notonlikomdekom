 # Chat TCP
 <div align="center">
  <img width="100%" src="https://capsule-render.vercel.app/api?type=waving&height=300&color=timeGradient&text=Not%20%Only%20%Kom%20De%20%Kom&reversal=true&fontAlign=50&animation=twinkling&textBg=false&stroke=ffffff&strokeWidth=4&fontColor=ffffff&fontSize=0" />
</div>

<p align="center">
  <img src="https://img.shields.io/badge/Status-🔥Cooked🔥-FF0000" />
  <img src="https://img.shields.io/badge/Version-1.0.0-brightgreen" />
  <img src="https://img.shields.io/badge/License-MIT-yellowgreen" />
  <img src="https://img.shields.io/badge/Built_With-Python-blue" />
</p>

<h1 align="center">
  <img src="https://readme-typing-svg.herokuapp.com?font=Fira+Code&pause=500&color=81a1c1&center=true&vCenter=true&width=600&lines=13523123,+13523161,+13523162,+and+13523163;Bimo,+Arlow,+Riza,+dan+Filbert" alt="R.Bimo, Arlow, Riza, dan Filbert" />
</h1>


## 📦 Table of Contents

- [🔍 Overview](#-overview)
- [📶 How To Run](#-how-to-run)
- [🤖 Referensi](#-referensi)
- [👤 Author & Pembagian Tugas](#-author)
- [♾️ License](#-license)

---

## 🔍 Overview

Aplikasi live-chat yang mensimulasikan koneksi TCP over UDP, tapi cooked sekali. Plz lab sister have mercy upon us!

### Fitur

* **Handshake mirip TCP** (SYN, SYN-ACK, ACK) dan penutupan FIN.
* **Heartbeat** tiap 1 detik + **AFK timeout** 30 detik.
* Perintah: `!disconnect`, `!change <nama>`, `!kill <password>`.

---

## 📶 How To Run

Follow these steps to get the application running on your local machine:

Note: Please have python 3.11 installed

0. **Make sure you have installed uv**

   a. Windows:
   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```
   b. MacOS and Linux:
   With curl:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

   With wget:
   ```bash
   wget -qO- https://astral.sh/uv/install.sh | sh
   ```

   Or you can also see the installation steps and documentation [here](https://docs.astral.sh/uv/getting-started/installation/#__tabbed_1_1)

2. **Download the ZIP Release**
   - Navigate to the repository’s releases page and download the latest zip file.

3. **Extract the ZIP File**
   - Unzip the downloaded file to your preferred location.

4. **Open (atleast 2) Terminals**
   - Open atleast two difference instances of terminal
   - Navigate both terminal (`cd`) to the folder where you extracted the project.

5. **Run**

   a. Terminal 1:
      ```bash
      uv run -m server
      ```
   b. Terminal 2 dan seterusnya:
      ```bash
      uv run -m client
      ```
---

## 🤖 Referensi

Kebanyakan sih dari Spesifikasi yang diberikan, namun ada beberapa yang dari ChatGPT dan Gemini

---

## 👤 Author

<table align="center">
  <tr>
    <th align="center">User</th>
    <th align="center">Job</th>
  </tr>
  <tr>
    <td align="center">
      <a href="https://github.com/Cola1000">
        <img src="https://avatars.githubusercontent.com/u/143616767?v=4" width="80px" style="border-radius: 50%;" alt="Cola1000"/><br />
        <sub><b>Rhio Bimo Prakoso S</b></sub>
      </a>
    </td>
    <td align="center">Setup, Segment (+Host, and README)</td>
  </tr>
  <tr>
    <td align="center">
      <a href="https://github.com/Arlow5761">
        <img src="https://avatars.githubusercontent.com/u/96019562?v=4" width="80px" style="border-radius: 50%;" alt="Arlow5761"/><br />
        <sub><b>Arlow Emmanuel Hergara</b></sub>
      </a>
    </td>
    <td align="center">Flow Control dan TCP</td>
  </tr>
  <tr>
    <td align="center">
      <a href="https://github.com/L4mbads">
        <img src="https://avatars.githubusercontent.com/u/85736842?v=4" width="80px" style="border-radius: 50%;" alt="L4mbads"/><br />
        <sub><b>Fachriza Ahmad Setiyono</b></sub>
      </a>
    </td>
    <td align="center">Client</td>
  </tr>
  <tr>
    <td align="center">
      <a href="https://github.com/filbertengyo">
        <img src="https://avatars.githubusercontent.com/u/163801345?v=4" width="80px" style="border-radius: 50%;" alt="filbertengyo"/><br />
        <sub><b>Filbert Engyo</b></sub>
      </a>
    </td>
    <td align="center">Server</td>
  </tr>
</table>

<div align="center" style="color:#6A994E;"> 🌿 Please Donate for Charity! 🌿</div>

<p align="center">
  <a href="https://tiltify.com/@cdawg-va/cdawgva-cyclethon-4" target="_blank">
    <img src="https://assets.tiltify.com/uploads/cause/avatar/4569/blob-9169ab7d-a78f-4373-8601-d1999ede3a8d.png" alt="IDF" style="height: 80px;padding: 20px" />
  </a>
</p>

---

## ♾️ License

This project is licensed under the MIT License
