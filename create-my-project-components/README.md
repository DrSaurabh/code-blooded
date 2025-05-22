# 🛠️ Create My Project Components

A Python utility to **automatically generate folder and file structures** for your projects, based on intuitive, human-readable structure definitions. Designed to simplify the process of creating complex folder and file structures and help you get started with your projects.

---

## 📦 Overview

Say goodbye to repetitive manual creation of boilerplate folders and files for your weekend projects. This script helps you:

- Parse a `project-structure` text file containing visual directory trees (as ASCII art).
- Create the entire project skeleton in your current working directory.
- Clean up everything just as easily if you want to start over.

---

## 🧱 Example: Input Structure

```
my-project/
├── bin/
│   ├── ls.py
│   ├── cat.py
├── core/
│   └── fs/
│       └── file_manager.py
```

---

## 🏗️ How It Works

1. The script parses the ASCII-art-style `project-structure` file.
2. Identifies hierarchy and relationships.
3. Converts this into a dictionary of paths.
4. Creates all files and folders in a sandboxed way under the specified project root.

> 🔒 All operations are confined to the local working directory for safety.

---

## 🚀 Getting Started

### 1. Download the script to a new, empty directory

1. Create a new directory and cd into it
1. Download the script from GitHub
1. Either manually by downloading the file or by using `curl -O https://raw.githubusercontent.com/DrSaurabh/code-blooded/main/create-my-project-components/project-builder.py`
1. You can also download the sample template if you want to try out things, or create one of your own.


### 2. Prepare Your Own Structure File

Create a file named `project-structure` and define your structure using readable indentation and lines.

Example:
```
my-project/
├── backend/
│   ├── Dockerfile
│   └── src/
│       └── app.py
```

### 3. Run the Script

```bash
python3 project-builder.py
```

Use the interactive menu to:
- Build the project
- Clean it up
- View debug logs as the script runs
- Restart the script live, in case you are making changes to the code and see where they lead. 

---

## ⚙️ Features

- 🧠 Intelligent parsing of project trees.
- 🔁 Restartable script engine.
- 🪵 Toggleable debug logs.
- 🧹 Safe and controlled cleanup modes.
- 🔧 Fully extensible and readable code.

---

## 🛡️ Safety Notes

- The root directory is **validated** to prevent accidental overwrites outside the project sandbox.
- The project root is **always manually created**, everything else is safe to clean/delete from script.
- Simple deletion through the script menu will only delete all files and folders created through the script.
- Forceful deletion through the script menu will delete everything within the project-root, except the `project-structure` and `project-builder.py` files.
---

## Author

**Saurabh Sawhney**  
Read the blog for this project on Medium to get a more in-depth overview and some really cool graphics.
(No blog of mine is behind paywalls and I do not want you to buy me any coffee).

---

## 📄 License

MIT License

Feel free to change whatever you wish.
---
