# Ollama Windows Portable

本仓库通过 GitHub Actions 构建 Ollama 的 Windows x64 便携包。手动运行
`Build Ollama for Windows` 工作流并输入 Ollama 版本号（不带 `v`），工作流会创建
`ollama-<version>-win-x64.zip` Release 资源。

手动测试可设置 `dry_run=true`：仍执行全部构建、程序启动检查及 ZIP 校验，产物保存为
保留 7 天的 Actions Artifact，跳过创建或更新 Release。为兼容现有 Builder 调用，
`dry_run` 默认 `false`；测试运行必须显式选择 `true`。

## 原生包布局与 CUDA 构建

Ollama 0.30 起，GGUF 推理服务不再包含在单个 Go 可执行文件中。便携包必须保留上游
`dist/windows-amd64` 的完整目录结构，不能只复制 `ollama.exe`：

```text
ollama.exe
lib/ollama/
├── llama-server.exe
├── llama-quantize.exe
├── CPU backend、基础 DLL 和其他原生 payload
├── cuda_v12/  # ggml-cuda.dll、cuBLAS、cuBLASLt、cuDART 及上游收集的依赖
└── cuda_v13/  # ggml-cuda.dll、cuBLAS、cuBLASLt 及上游收集的依赖
```

缺少 `lib/ollama/llama-server.exe` 时，`ollama.exe` 仍可能通过 `--version` 检查，
但加载模型会报 `llama-server binary not found`。缺少 CUDA backend 时，即便机器
安装了 NVIDIA 驱动，包也无法提供对应的 CUDA 推理能力。

原生构建工作流使用 Windows 2022、MSVC 2022 和 Ninja，先执行上游
`scripts/build_windows.ps1 cpu ollama`，再安装官方 CUDA 12.8、13.0 工具链并依次执行
`cuda12`、`cuda13`。CPU 构建会清理输出目录，必须先于 CUDA 构建。GPU 运行库由上游
CMake install 收集，工作流保留整个 `dist/windows-amd64` 目录结构打入 ZIP。

工具链安装失败、`nvcc` 缺失或版本不符均立即失败。上游可能在找不到 CUDA 时跳过
构建，因此还会分别校验 staging 目录和最终 ZIP：基础程序、MinGW 运行库、两个 CUDA
backend 及其必要运行库必须存在且非空，ZIP 还要通过 CRC 检查；失败时不能进入
Release 步骤。CUDA 13 的必需文件按官方 0.34.4 ZIP 核对，没有将其不包含的独立
`cudart64_13.dll` 列为必需文件。本次不增加 ROCm、Vulkan 或 MLX 构建。

较旧、尚无 `llama/server` 新源码布局的版本保留 Go-only fallback 及 MinGW 运行库，
不适用上述原生 payload 和 CUDA 目录要求。

## 验证

仓库回归测试仅使用 Python 标准库，工作流编译前也会执行：

```sh
python -B -m unittest discover -s tests -v
python .github/scripts/verify_payload.py --payload staging/payload --layout native
python .github/scripts/verify_payload.py --archive ollama-0.34.4-win-x64.zip --layout native
```

旧源码布局使用 `--layout legacy`。测试覆盖 CPU-only 包、逐个缺失或空文件、损坏 ZIP、
完整包以及 legacy 兼容。工作流另保留隔离 PATH 下运行 `ollama.exe --version` 和
`llama-server.exe --version` 的检查，避免 runner 上的额外 DLL 掩盖缺失依赖。

这些检查证明包内容满足要求，不能代替真实 GPU 验收。发布验收需要在安装 NVIDIA
驱动的 Windows 机器上启动包内服务、加载模型，从日志确认 CUDA backend 被加载，
并用 `ollama ps` 检查模型实际使用 GPU。上下文长度及显存容量可能使部分层留在 CPU，
不要求所有模型一律显示 100% GPU。

工作流代码修复不会自动更新已经发布的 ZIP 或 ServBay 分发包；已有 CPU-only 包仍需
经过获准的重新构建与下游发布流程替换。操作时应确认 11434 端口对应的服务进程，
避免将另一套 Ollama 的运行结果当作本包验收结果。
