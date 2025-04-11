# 🌲 GoRoot

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
**GoRoot** is a powerful command-line tool designed to simplify Go project management and execution.

## ✨ Features

- **Project Initialization** - Set up new Go projects with proper structure
- **Build Automation** - Compile your Go projects with ease
- **Execution Control** - Run Go files directly with support for arguments
- **Flexible Usage** - Target specific files or modules for execution

## 📦 Build && Installation From Source

```bash
# Clone the repository
git clone https://github.com/cazzano/goroot.git

# Navigate to the directory
cd goroot/stable/go/src/

# Install the tool
go build && mv hello goroot && sudo mv goroot /usr/bin && echo "You Installed It Hah !!!"
```
## Installation From Release

```bash
curl -L -o goroot_vr-1.0_x86_64_arch.zip https://github.com/cazzano/goroot/releases/download/go/goroot_vr-1.0_x86_64_arch.zip

unzip goroot_vr-1.0_x86_64_arch.zip && sudo mv goroot /usr/bin/ && rm goroot_vr-1.0_x86_64_arch.zip && echo "You Installed It Bro!!!!"
```

## 🚀 Usage

GoRoot provides several commands to simplify your Go development workflow:

### Initialize an existing project with go.mod

```bash
goroot init
```

This will create a go.mod file in the current directory.

### Create a new project

```bash
goroot new my-project
```

This will create a project structure:

```
my-project/
├── src/
├── target/
└── go.mod
```

### Build your project

```bash
goroot build
```

Compiles your Go project and produces an executable binary in the `target/release/` directory.

### Run Go files

Run Go files in the current directory:

```bash
goroot run
```

Run with arguments (supports up to 10 arguments):

```bash
goroot run arg1 arg2 arg3
```

### Run a specific file or module

```bash
goroot run --1 ./path/to/file.go
```

```bash
goroot run --1 specific-module.go
```

### Display version information

```bash
goroot --v
```

### Display help message

```bash
goroot --h
```

## 📝 Examples

### Example 1: Quick Start Project

```bash
# Create a new project
goroot new my-awesome-app

# Navigate to the source directory
cd my-awesome-app/src

# Run the project
goroot run

# Build the project
goroot build
# Your compiled binary will be in my-awesome-app/target/release/
```

### Example 2: Running with Arguments

```bash
# Run a file with command-line arguments
goroot run config.json --verbose debug
```

### Example 3: Working with Specific Files

```bash
# Run a specific file
goroot run --1 help.go

# Run a specific module
goroot run --1 warn.go
```

## 🛠️ Command Reference

| Command | Description |
|---------|-------------|
| `init` | Initialize the existing project with go.mod |
| `new` | Initialize a new project structure |
| `build` | Build the project |
| `run` | Run Go files in the current directory (max 10 arguments) |
| `run --1` | Run a specific file or module |
| `--v` | Display version information |
| `--h` | Display help message |

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📞 Support

For support, please open an issue in the GitHub repository or contact the maintainers.
