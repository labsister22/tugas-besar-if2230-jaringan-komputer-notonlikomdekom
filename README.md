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

## 🔍 Overview

Du weißt vielleicht schon, dass dieser Kurs eigentlich nach IF2130 „Betriebssysteme“ belegt werden sollte. Und das aus gutem Grund. Betriebssysteme sind im wahrsten Sinne des Wortes Voraussetzung für diesen Kurs. Daneben scheinen auch viele andere Kurse den Schwierigkeitsgrad/Arbeitsaufwand ihrer Aufgaben zu erhöhen, vielleicht jeder aus eigenen Gründen. Das macht dein akademisches Erlebnis ziemlich einzigartig und auch sehr stressig. Falls es dir noch niemand gesagt hat: Du machst das schon großartig, dass du es so weit geschafft hast.

Es war ein ziemlich hektisches Semester, nicht nur für euch, sondern auch für uns. Wusstet ihr, dass in den Stundenplänen nicht einmal Platz für die Laborarbeit für diesen Kurs war, weshalb wir sie auf zwei Sitzungen aufteilen mussten? Ja, das war nicht lustig. Die Stundenpläne für dieses Semester sind wirklich schrecklich. Eigentlich sollte die Laborarbeit in der Woche nach den Zwischenprüfungen enden. Aber wegen zwei zusätzlichen Feiertagen (die eine Woche nicht nutzen konnten) und auch wegen des verzögerten Beginns aus anderen Gründen, wurde es am Ende ziemlich spät. Wir entschuldigen uns aufrichtig, falls ihr den Stundenplan ungünstig oder unpassend findet.

Wie dem auch sei, wir glauben, dass wir den Schwierigkeitsgrad dieses Projekts reduziert haben und es einigermaßen in Ordnung ist. Hoffentlich ist es jetzt nicht zu schwierig. Es ist zwar immer noch recht langwierig, aber angesichts der Verwendung des berüchtigten Python und der Existenz von LLMs halten wir den Arbeitsaufwand für angemessen. Nicht, dass die Verwendung von LLMs von Ihnen erwartet wird. Leider muss das Projekt einfach so gestaltet sein, dass Studierende, die das Ganze mit KI-Code ausprobieren möchten, zumindest verstehen müssen, was der von der KI bereitgestellte Code bewirkt.

In diesem Sinne hoffen wir, dass Sie KI sinnvoll einsetzen und dem wirklichen Verständnis des Materials Priorität einräumen. Denken Sie daran, dass es sich um ein Werkzeug handelt und Sie mehr davon haben, wenn Sie sich weiter mit den Themen befassen, anstatt einfach nach dem Code zu fragen, der Ihnen auf dem Silbertablett serviert wird. Es ist uns egal, ob Sie kopieren und einfügen. Uns ist wichtig, dass Sie sich bemühen, jeden Code zu verstehen, den Sie kopieren und einfügen.

## 📶 How To Run

Follow these steps to get the application running on your local machine:

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
   b. Terminal 2:
      ```bash
      uv run -m client
      ```
   c. Terminal 1:
      ```bash
      python -m packages.server.src.server.server
      ```
   d. Terminal 2:
      ```bash
      python -m packages.client.src.client.client
      ```


## 🤖 Referensi

Kebanyakan sih dari Spesifikasi yang diberikan, namun ada beberapa yang dari ChatGPT

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
