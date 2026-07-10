# Ollama Windows Portable

本仓库通过 GitHub Actions 构建 Ollama 的 Windows x64 便携包。手动运行
`Build Ollama for Windows` 工作流并输入 Ollama 版本号（不带 `v`），工作流会创建
`ollama-<version>-win-x64.zip` Release 资源。

## 包内布局

Ollama 0.30 起，GGUF 推理服务不再包含在单个 Go 可执行文件中。便携包必须保留上游
`dist/windows-amd64` 的完整目录结构，不能只复制 `ollama.exe`：

```text
ollama.exe
lib/ollama/
├── llama-server.exe
├── llama-quantize.exe
└── 运行时所需的 DLL 和其他原生 payload
```

缺少 `lib/ollama/llama-server.exe` 时，`ollama.exe` 仍可能通过 `--version` 检查，
但加载模型会报 `llama-server binary not found`。因此工作流对新源码布局调用上游
`scripts/build_windows.ps1 cpu ollama`，验证上述两个原生程序后，将完整 payload 打入
ZIP。

当前工作流构建的是上游 CPU/base payload，不额外安装 CUDA、ROCm、Vulkan 或 MLX
工具链；包可以完成 CPU 推理，但不会包含这些可选 GPU backend。若后续加入 GPU 包，
仍需保持同一个 `lib/ollama` 目录契约并将对应 backend 子目录完整打包。

较旧、尚无 `llama/server` 新源码布局的版本保留 Go-only fallback；这类旧包只有
`ollama.exe`，不适用 0.30 以后的原生 payload 要求。
