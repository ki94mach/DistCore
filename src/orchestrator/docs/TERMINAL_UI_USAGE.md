# Terminal UI Module Usage

The `terminal_ui.py` module provides reusable terminal formatting utilities for creating beautiful, colored command-line interfaces.

## Features

- ✅ Cross-platform ANSI color support (Windows, Linux, macOS)
- ✅ Automatic Windows ANSI enablement for Anaconda Prompt
- ✅ Terminal-friendly symbols that work in all terminals
- ✅ Multiple usage patterns (module-level functions or class-based)

## Quick Start

### Option 1: Using Module-Level Functions (Recommended)

```python
from src.orchestrator.ui.terminal_ui import (
    Colors,
    print_header,
    print_success,
    print_error,
    print_warning,
    print_info,
    print_action,
    print_menu_item,
    print_prompt,
    colorize
)

# Print formatted messages
print_header("My Application", Colors.BRIGHT_CYAN)
print_success("Operation completed successfully!")
print_error("Something went wrong!")
print_warning("This is a warning")
print_info("Here's some information")
print_action("Processing data...")

# Print menu items
print_menu_item('1', 'Option One', Colors.BRIGHT_WHITE)
print_menu_item('2', 'Option Two', Colors.WHITE)

# Get user input with colored prompt
user_input = print_prompt("Enter your choice: ")

# Custom colored text
colored_text = colorize("Important text", Colors.BRIGHT_RED)
print(colored_text)
```

### Option 2: Using the TerminalUI Class

```python
from src.orchestrator.ui.terminal_ui import TerminalUI, Colors

# Create an instance (customizable separator width)
ui = TerminalUI(separator_width=80)

# Use instance methods
ui.print_header("My Application", Colors.BRIGHT_CYAN)
ui.print_success("Operation completed!")
ui.print_error("Error occurred!")
user_input = ui.print_prompt("Enter value: ")
```

## Available Colors

```python
from src.orchestrator.ui.terminal_ui import Colors

# Standard colors
Colors.BLACK, Colors.RED, Colors.GREEN, Colors.YELLOW
Colors.BLUE, Colors.MAGENTA, Colors.CYAN, Colors.WHITE

# Bright colors (recommended for better visibility)
Colors.BRIGHT_BLACK, Colors.BRIGHT_RED, Colors.BRIGHT_GREEN
Colors.BRIGHT_YELLOW, Colors.BRIGHT_BLUE, Colors.BRIGHT_MAGENTA
Colors.BRIGHT_CYAN, Colors.BRIGHT_WHITE

# Background colors
Colors.BG_RED, Colors.BG_GREEN, Colors.BG_YELLOW, Colors.BG_BLUE

# Styles
Colors.BOLD, Colors.DIM, Colors.UNDERLINE
```

## Available Symbols

```python
from src.orchestrator.ui.terminal_ui import Symbols

Symbols.CHECK      # '[OK]'
Symbols.CROSS      # '[X]'
Symbols.ARROW     # '->'
Symbols.WARNING    # '[!]'
Symbols.INFO      # '[i]'
Symbols.QUESTION  # '[?]'
Symbols.SEPARATOR # '='
```

## Example: Complete CLI Application

```python
from src.orchestrator.ui.terminal_ui import (
    Colors,
    print_header,
    print_success,
    print_error,
    print_info,
    print_menu_item,
    print_prompt
)

def main():
    print_header("My CLI Application", Colors.BRIGHT_CYAN)

    print_info("\nAvailable Options:")
    print_menu_item('1', 'Run Process', Colors.BRIGHT_WHITE)
    print_menu_item('2', 'View Status', Colors.WHITE)
    print_menu_item('q', 'Quit', Colors.BRIGHT_YELLOW)

    choice = print_prompt("\nSelect option: ").strip().lower()

    if choice == '1':
        print_info("Running process...")
        # ... do work ...
        print_success("Process completed!")
    elif choice == '2':
        print_info("Status: Running")
    elif choice == 'q':
        print_info("Goodbye!")
    else:
        print_error("Invalid choice!")

if __name__ == '__main__':
    main()
```

## Platform Support

- ✅ **Windows 10+**: Full ANSI color support (automatically enabled)
- ✅ **Anaconda Prompt**: Full support
- ✅ **Linux/macOS**: Native ANSI support
- ✅ **Git Bash**: Full support
- ✅ **PowerShell**: Full support (Windows 10+)

## Notes

- Colors are automatically enabled on Windows 10+ when the module is imported
- If colors don't work, the module gracefully falls back to plain text
- All symbols use ASCII characters for maximum compatibility
- The module is lightweight with no external dependencies
