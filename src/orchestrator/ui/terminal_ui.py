"""Terminal UI utilities for colored output and formatting.

This module provides reusable terminal formatting utilities including:
- ANSI color codes for cross-platform terminal output
- Terminal-friendly symbols
- Formatted print functions for different message types
- Automatic Windows ANSI support for Anaconda Prompt and modern terminals
"""

import sys


# Enable ANSI color support on Windows
if sys.platform == 'win32':
    try:
        # Enable ANSI escape sequences on Windows 10+
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except:
        pass


class Colors:
    """ANSI color codes for terminal output."""
    # Reset
    RESET = '\033[0m'
    
    # Text colors
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'
    
    # Bright colors
    BRIGHT_BLACK = '\033[90m'
    BRIGHT_RED = '\033[91m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_BLUE = '\033[94m'
    BRIGHT_MAGENTA = '\033[95m'
    BRIGHT_CYAN = '\033[96m'
    BRIGHT_WHITE = '\033[97m'
    
    # Background colors
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_YELLOW = '\033[43m'
    BG_BLUE = '\033[44m'
    
    # Styles
    BOLD = '\033[1m'
    DIM = '\033[2m'
    UNDERLINE = '\033[4m'


class Symbols:
    """Terminal-friendly symbols that work in Windows/Anaconda Prompt."""
    CHECK = '[OK]'
    CROSS = '[X]'
    ARROW = '->'
    WARNING = '[!]'
    INFO = '[i]'
    QUESTION = '[?]'
    SEPARATOR = '='


class TerminalUI:
    """Terminal UI utility class for formatted output."""
    
    def __init__(self, separator_width: int = 60):
        """
        Initialize TerminalUI.
        
        Args:
            separator_width: Width of separator lines for headers (default: 60)
        """
        self.separator_width = separator_width
    
    def colorize(self, text: str, color: str) -> str:
        """
        Apply color to text.
        
        Args:
            text: Text to colorize
            color: Color code from Colors class
            
        Returns:
            Colored text string
        """
        return f"{color}{text}{Colors.RESET}"
    
    def print_header(self, text: str, color: str = Colors.CYAN) -> None:
        """
        Print a formatted header with separator lines.
        
        Args:
            text: Header text
            color: Color for the header (default: CYAN)
        """
        separator = Symbols.SEPARATOR * self.separator_width
        print(f"\n{self.colorize(separator, color)}")
        print(self.colorize(f"{text:^{self.separator_width}}", color))
        print(self.colorize(separator, color))
    
    def print_success(self, text: str) -> None:
        """
        Print success message with green color.
        
        Args:
            text: Success message
        """
        print(self.colorize(f"{Symbols.CHECK} {text}", Colors.BRIGHT_GREEN))
    
    def print_error(self, text: str) -> None:
        """
        Print error message with red color.
        
        Args:
            text: Error message
        """
        print(self.colorize(f"{Symbols.CROSS} {text}", Colors.BRIGHT_RED))
    
    def print_warning(self, text: str) -> None:
        """
        Print warning message with yellow color.
        
        Args:
            text: Warning message
        """
        print(self.colorize(f"{Symbols.WARNING} {text}", Colors.BRIGHT_YELLOW))
    
    def print_info(self, text: str) -> None:
        """
        Print info message with cyan color.
        
        Args:
            text: Info message
        """
        print(self.colorize(f"{Symbols.INFO} {text}", Colors.BRIGHT_CYAN))
    
    def print_action(self, text: str) -> None:
        """
        Print action message with blue color.
        
        Args:
            text: Action message
        """
        print(self.colorize(f"{Symbols.ARROW} {text}", Colors.BRIGHT_BLUE))
    
    def print_menu_item(self, key: str, text: str, color: str = Colors.WHITE) -> None:
        """
        Print a menu item.
        
        Args:
            key: Menu key/option
            text: Menu item text
            color: Color for the menu item (default: WHITE)
        """
        print(self.colorize(f"  {key}. {text}", color))
    
    def print_prompt(self, text: str, color: str = Colors.BRIGHT_WHITE) -> str:
        """
        Print a prompt and return user input.
        
        Args:
            text: Prompt text
            color: Color for the prompt (default: BRIGHT_WHITE)
            
        Returns:
            User input string
        """
        return input(self.colorize(f"{text}", color))
    
    def print_hint(self, text: str) -> None:
        """
        Print a hint/help text with dim color.
        
        Args:
            text: Hint text
        """
        print(self.colorize(text, Colors.DIM))
    
    def print_value(self, label: str, value: any, color: str = Colors.BRIGHT_WHITE) -> None:
        """
        Print a label-value pair.
        
        Args:
            label: Label text
            value: Value to display
            color: Color for the value (default: BRIGHT_WHITE)
        """
        print(f"{label}: {self.colorize(str(value), color)}")


# Convenience functions for direct use (module-level)
def colorize(text: str, color: str) -> str:
    """Apply color to text."""
    return f"{color}{text}{Colors.RESET}"


def print_header(text: str, color: str = Colors.CYAN, width: int = 60) -> None:
    """Print a formatted header."""
    separator = Symbols.SEPARATOR * width
    print(f"\n{colorize(separator, color)}")
    print(colorize(f"{text:^{width}}", color))
    print(colorize(separator, color))


def print_success(text: str) -> None:
    """Print success message."""
    print(colorize(f"{Symbols.CHECK} {text}", Colors.BRIGHT_GREEN))


def print_error(text: str) -> None:
    """Print error message."""
    print(colorize(f"{Symbols.CROSS} {text}", Colors.BRIGHT_RED))


def print_warning(text: str) -> None:
    """Print warning message."""
    print(colorize(f"{Symbols.WARNING} {text}", Colors.BRIGHT_YELLOW))


def print_info(text: str) -> None:
    """Print info message."""
    print(colorize(f"{Symbols.INFO} {text}", Colors.BRIGHT_CYAN))


def print_action(text: str) -> None:
    """Print action message."""
    print(colorize(f"{Symbols.ARROW} {text}", Colors.BRIGHT_BLUE))


def print_menu_item(key: str, text: str, color: str = Colors.WHITE) -> None:
    """Print a menu item."""
    print(colorize(f"  {key}. {text}", color))


def print_prompt(text: str, color: str = Colors.BRIGHT_WHITE) -> str:
    """Print a prompt and return user input."""
    return input(colorize(f"{text}", color))


def print_hint(text: str) -> None:
    """Print a hint/help text."""
    print(colorize(text, Colors.DIM))


def print_value(label: str, value: any, color: str = Colors.BRIGHT_WHITE) -> None:
    """Print a label-value pair."""
    print(f"{label}: {colorize(str(value), color)}")

