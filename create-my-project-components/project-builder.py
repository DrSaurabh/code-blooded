# version 1.1.0
# Changelog: added variable "ignore_directories", which will not be part of the printed project tree

import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple
import re
from pprint import pprint
from time import sleep
from shutil import rmtree 

restart_quickness = 0.1
restart_dots = 6
debugger_mode=False
ignore_directories = ["__pycache__", ".git", ".vscode", ".idea", ".DS_Store"]
def debug(*args, **kwargs):
    if debugger_mode: print(*args)
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    RESET = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
def clear_screen():
    """Clear the terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')    
def parse_structure_file(file_path="project-structure"):
    """
    Parse the project-structure file into a hierarchical dictionary and return a dictionary of heirarchy information.
    """  
    # PART 1: Check if the project-structure file exists. 
    if not os.path.isfile(file_path):
        print(f"{Colors.RED}{file_path} not found. Exiting program.{Colors.RESET}")
        sys.exit(1)

    # PART 2: Read the project-structure file    
    with open(file_path, 'r') as f:
        lines_dict = {}
        for idx, line in enumerate(f.readlines(),start=1):
            if '#' in line: line = line.split('#')[0]
            line = line.rstrip()
            if not line: continue
            if not (any(char.isalnum() for char in line)): continue # check for atleast one alphanumeric character
            lines_dict[idx] = {"line": line,
                            "directory": line[-1] == "/",
                            "parent_idx": None,
                            "parent_name": None,
                                }

    # There may be multiple | characters in a line, so we need to find the one closest to the name of the file/directory
    # And we need to go bottoms up, trying to find the parent of each line 
    
    # PART 3: The first loop    
    for idx in range(max(lines_dict.keys()),0,-1): # populating lines_dict with positional information about art and names
        line = lines_dict.get(idx)
        if not line: continue
        line = line["line"]
        ["line"]
        debug(f"[ {idx} ] {line}")
        # position of alphanumeric character in the line
        pos_of_filefolder_name = next((i for i, c in enumerate(line) if c.isalnum()), None)
        debug("position of alphanumeric character in the line:",pos_of_filefolder_name)
        lines_dict[idx]["pos_of_filefolder_name"] = pos_of_filefolder_name

        # length of the alphanumeric block in the line
        length_of_filefolder_name = len(line)-pos_of_filefolder_name
        debug("Length of folder/filename:", length_of_filefolder_name)
        lines_dict[idx]["length_of_filefolder_name"] = length_of_filefolder_name

        # position of the non-alphanumeric non-space character in the line closest to the alphanumeric character
        # we need to move leftwards from the position of the alphanumeric character
        # and find the first non-alphanumeric non-space character
        # and the first space after this character

        pos_of_art = -1 # a default value for when we don't find any art. Banksy, where are you?
        if idx == 1: continue # first line is the root directory
        closest_space_discovered_flag = 0
        closest_art_discovered_flag = 0
        for i in range(pos_of_filefolder_name,-1,-1):
            if line[i] == " " and closest_space_discovered_flag == 0:
                debug('closest_space_discovered_flag triggered at pos:', i)
                closest_space_discovered_flag = 1
                continue # the first space preceeding the alphanumeric character
            if not (line[i].isalnum()) and line[i] != " " and closest_art_discovered_flag == 0:
                debug('closest_art_discovered_flag triggered at pos:', i)  
                closest_art_discovered_flag = 1 # now we have a space and art discovered. Time to look for the next space
            if line[i] == " " and closest_space_discovered_flag == 1 and closest_art_discovered_flag == 1:
                pos_of_art = i+1
                break
            if i == 0 and closest_space_discovered_flag == 1 and closest_art_discovered_flag == 1:
                pos_of_art = 0 # we found both flags but no space before the art. So the art is at the beginning of the line
                break

        debug("position of closest ASCII art:",pos_of_art)
        lines_dict[idx]["pos_of_art"] = pos_of_art

        # total number of contiguous blocks of non-alphanumeric non-space characters to the left of the first alphanumeric character
        number_of_art_blocks = len(re.findall(r'[^a-zA-Z0-9\s]+', line[:pos_of_filefolder_name]))
        debug("number of distinct ASCII art:", number_of_art_blocks); debug("")
        lines_dict[idx]["number_of_art_blocks"] = number_of_art_blocks

        # is the position of the non-alphanumeric non-space character in the line closest to the alphanumeric character
        # within the extent of the alphanumeric block in the line immediately above

    # PART 4 The parent-searcher nested loops
    for idx in range(max(lines_dict.keys()),0,-1): # finding the parent
        if idx == 1: continue # first line is the root directory
        # if the line is not a child, then continue
        if not lines_dict.get(idx): continue        
        debug("")
        debug(f"[ {idx} ]: {idx}")
        debug(f"childname:", lines_dict.get(idx)['line'][lines_dict.get(idx)['pos_of_filefolder_name']:])
        debug("pos_of_art", lines_dict.get(idx)["pos_of_art"])
        debug("pos_of_filefolder_name", lines_dict.get(idx)["pos_of_filefolder_name"])
        debug("length_of_filefolder_name", lines_dict.get(idx)["length_of_filefolder_name"])
        # we need to loop through the lines above this line till we find a parent
        pos_of_art = lines_dict.get(idx)["pos_of_art"] # position of art for the child
        for idx_above in range(idx-1,0,-1):
            # if the line above is not a parent, then continue
            if not lines_dict.get(idx_above): continue
            pos_of_parent_filefolder_name = lines_dict.get(idx_above)["pos_of_filefolder_name"]
            length_of_parent_filefolder_name = lines_dict.get(idx_above)["length_of_filefolder_name"]
            debug(f"checking line {idx_above} for parent")
            # if art for the child line hits the alphanumeric for the plausible parent, then bingo, we have it 
            if pos_of_art >= pos_of_parent_filefolder_name and pos_of_art <= (pos_of_parent_filefolder_name + length_of_parent_filefolder_name):
                parent_name = lines_dict.get(idx_above)['line'][lines_dict.get(idx_above)['pos_of_filefolder_name']:]
                debug("found parent at line", idx_above)
                debug("Parent's name:", parent_name)
                lines_dict[idx]["parent_idx"] = idx_above
                lines_dict[idx]["parent_name"] = parent_name
                break

    return lines_dict
def generate_paths(lines_dict):
    """Analyze the paths and create a linear string for each path."""
    project_structure_paths = []
    root_path = lines_dict.get(1)["line"][lines_dict.get(1)["pos_of_filefolder_name"]:]
     
    for idx, line_info in lines_dict.items():
        # I need to combine the child with the parent, till i reach the root
        path = line_info["line"][line_info["pos_of_filefolder_name"]:]
        parent_idx = line_info["parent_idx"]
        while parent_idx is not None:
            parent_info = lines_dict.get(parent_idx)
            if parent_info:
                to_append = parent_info["line"][parent_info["pos_of_filefolder_name"]:]
                separator = "" if to_append.endswith("/") else "/"
                path = to_append + separator + path
                parent_idx = parent_info["parent_idx"]
            else:
                break
        debug(path)   
        project_structure_paths.append(path)

    # Now we need to remove the root directory from the path
    project_structure_paths = [path.replace(root_path, "./") for path in project_structure_paths]
    project_structure_paths = project_structure_paths[1:] # removing the root directory from the list
    return project_structure_paths
def create_project_structure(project_structure_paths):
    """Create the project structure based on the parsed paths."""
    updated_any = False
    for path in project_structure_paths:
        try:
            if path.endswith("/"):
                # Directory
                if not os.path.isdir(path):
                    os.makedirs(path, exist_ok=True)
                    updated_any = True
                else:
                    debug(f"Directory already exists: {path} ... skipping")

            else:
                # File
                try:
                    f = open(path, "r")
                    debug(f"File already exists: {path} ... skipping")
                    f.close()
                except FileNotFoundError:
                    with open(path, "w") as f:
                        f.write("")
                        updated_any = True
        except Exception as e:
            debug(f"{Colors.RED}Error creating {path}: {str(e)}{Colors.RESET}")

    if updated_any:
        project_structure_action = "updated"
    else:
        project_structure_action = "no changes made"
            
    return project_structure_action        
def cleanup_project_structure(project_structure_paths, forceful=False):
    """Cleanup the project structure based on the parsed paths."""
    directories_to_remove = []
    try:
        for path in project_structure_paths:
            if os.path.isdir(path):
                directories_to_remove.append(path)    
            else:
                os.remove(path)
    except Exception as e:
        debug(f"{Colors.RED}Error deleting {path}: {str(e)}{Colors.RESET}")
    # now that all files are deleted, we need to remove the directories        
   
    directories_to_remove = sorted(directories_to_remove, key=len, reverse=True) # sort by length to remove inner directories first
    for path in directories_to_remove:
        try:
            os.rmdir(path)
        except Exception as e: # manually created files left over
            debug(f"{Colors.RED}Retaining occupied directory {path}:{Colors.RESET}")


    if forceful:
        for root, dirs, files in os.walk(os.getcwd()):
                for file in files:
                    if file not in ["project-structure", "project-builder.py"]:
                        print(f"{Colors.RED}Forcefully deleting file: {file}{Colors.RESET}")
                        os.remove(os.path.join(root, file))
                for dir in dirs:
                    print(f"{Colors.RED}Forcefully deleting directory {dir}{Colors.RESET}")
                    rmtree(dir)

    message = "project-structure based" if not forceful else "FORCEFUL"
    print(f"{Colors.YELLOW}{message} cleanup complete.{Colors.RESET}")        
def print_tree(base_path: Path = Path('.'), prefix: str = ""):
    """Print the directory structure in tree format with colors."""
    if base_path.name in ignore_directories:
        return
    try:
        contents = sorted(os.listdir(base_path))
        if not contents:
            return            
        pointers = ["├── "] * (len(contents) - 1) + ["└── "]
        
        for pointer, item in zip(pointers, contents):
            path = base_path / item # / operator to concatenate the base_path and item to form a new path.
            if path.name in ignore_directories: continue
            if path.is_dir():
                color = Colors.YELLOW
            else:
                color = Colors.GREEN
            print(prefix + pointer + color + item + Colors.RESET)
            
            if path.is_dir():
                extension = "    " if pointer == "└── " else "│   "
                print_tree(path, prefix + extension)
    except Exception as e:
        print(f"{Colors.RED}Error walking directory {base_path}: {str(e)}{Colors.RESET}")
def show_menu():
    """Display the interactive menu."""
    print(f"\n{Colors.BOLD}=== Project Builder Menu ==={Colors.RESET}")
    print(f"{Colors.CYAN}1  Show current structure{Colors.RESET}")
    print(f"{Colors.CYAN}2  Analyze project-structure file{Colors.RESET}")
    print(f"{Colors.CYAN}3  Create project structure{Colors.RESET}")
    print(f"{Colors.CYAN}4  Cleanup project structure{Colors.RESET}")
    print(f"{Colors.RED}4f Forceful cleanup{Colors.RESET}")
    print(f"{Colors.CYAN}r  Restart this script{Colors.RESET}")
    print(f"{Colors.CYAN}t  Debugger Mode Toggler  [current status: debugger mode ", end="")
    if debugger_mode: print(f"{Colors.RED}ON{Colors.RESET} ]")
    else: print(f"{Colors.GREEN}OFF{Colors.RESET} ]")
    print(f"{Colors.CYAN}c  Clear screen{Colors.RESET}")    
    print(f"{Colors.CYAN}x  Exit{Colors.RESET}")
    
    try:
        choice = input(f"\n{Colors.BOLD}Enter your choice: {Colors.RESET}")
        return choice
    except ValueError:
        return -1
def main():
    global debugger_mode
    working_dir = Path('.').absolute()
    print(f"\n{Colors.BOLD}=== Project Builder ==={Colors.RESET}")
    print(f"pwd:  {working_dir}")
    while True:
        choice = show_menu().lower()
        lines_dict = parse_structure_file()
        project_structure_paths = generate_paths(lines_dict)
        actual_project_root = os.path.split(os.getcwd())[1]
        stated_project_root = lines_dict.get(1)["line"][lines_dict.get(1)["pos_of_filefolder_name"]:].rstrip("/")
        if stated_project_root != actual_project_root:
            print(f"{Colors.RED}Project root in project-structure file does not match working directory.{Colors.RESET}")
            print(f"  Root as per project-structure: {Colors.BOLD}{stated_project_root}{Colors.RESET}")
            print(f"      Current working directory: {Colors.BOLD}{actual_project_root}{Colors.RESET}")
            print(f"Please update the project-structure file to match the current working directory.{Colors.RESET}")
            print("    OR")
            print(f"Move operations to the correct directory.{Colors.RESET}")
            exit(1)
        if choice == "c": # clear screen
            clear_screen()
        elif choice == "1": # current structure
            print(f"\n{Colors.BOLD}Current project structure:{Colors.RESET}")
            print(f"[{Colors.YELLOW}  directories    {Colors.GREEN}files{Colors.RESET}  ]")
            print()
            print(f"{Colors.YELLOW}{actual_project_root}{Colors.RESET}")
            print_tree()
            print()
        elif choice == "2": # parse  and analyse project-structure file 
            print(f"\n{Colors.BOLD}Parsed project structure paths:{Colors.RESET}")
            for path in project_structure_paths:
                print(f"  {Colors.GREEN}{path}{Colors.RESET}")
        elif choice == "3": # create project structure
            print(f"{Colors.YELLOW}Creating project structure...{Colors.RESET}")
            project_structure_action = create_project_structure(project_structure_paths)
            print(f"{Colors.BOLD}Project structure {project_structure_action}.{Colors.RESET}")
            print()
            print(f"{Colors.YELLOW}{stated_project_root}{Colors.RESET}")
            print_tree()        
        elif choice in ["4", "4f"]:  # cleanup project structure
            print(f"{Colors.YELLOW}Cleaning up project structure...\n{Colors.RESET}")
            if choice == "4":
                warning = f"{Colors.YELLOW}This will remove {Colors.RED}ALL{Colors.YELLOW} files and directories\nspecified in the project-structure file{Colors.RESET}"
            if choice == "4f":
                warning = f"{Colors.YELLOW}This will {Colors.RED}REMOVE ALL{Colors.YELLOW} files and directories\nin the current working directory,\nexcept \"project-structure\" and \"project-builder.py\"{Colors.RESET}"    
            print(warning)   
            confirmation = input(f"{Colors.YELLOW}\n- press y or Y to confirm or any other key to abort mission{Colors.RESET}\n")
            if confirmation.lower() == "y":
                cleanup_project_structure(project_structure_paths, forceful=True if choice == "4f" else False)
            else: 
                print(f"{Colors.YELLOW}Aborting cleanup operation.{Colors.RESET}")
        elif choice == "x": # exit
            print(f"\n{Colors.GREEN}Exiting Project Builder.{Colors.RESET}")
            sys.exit(0)
        elif choice == "r": # restart
            print("Restarting application ", end="", flush=True)
            for _ in range(restart_dots):
                sleep(restart_quickness)
                print(".", end="", flush=True)
            clear_screen()
            os.execv(sys.executable, [sys.executable] + sys.argv)      
        elif choice in ["t", "d"]: # Toggle debugger mode  
            debugger_mode= not(debugger_mode)
        else: # invalid choice catcher
            print(f"\n{Colors.RED}{choice} is an invalid choice. Please select from the menu options only.{Colors.RESET}")
if __name__ == "__main__":
    main()
