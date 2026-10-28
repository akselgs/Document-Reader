import shlex
import subprocess

modelpath = "/share/home/student14/model/files/granite-docling-258M-Q8_0.gguf"
mmprojpath = "/share/home/student14/model/files/MMPROJ_FILE_NAME.gguf"  # fill in
imagepath = "/share/home/student14/model/test/example_page.png"
exepath = "/share/home/student14/model/llama.cpp/build/bin/llama-mtmd-cli"
prompt = "Convert this page to docling."
more_params = "-c 4096 -n 2048 -t 4 --temp 0"

cmd = [
    exepath,
    "-m", modelpath,
    "--mmproj", mmprojpath,
    "--image", imagepath,
    "-p", prompt,
    *shlex.split(more_params),
]
def main():
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"llama-mtmd-cli failed:\n{result.stderr}")
    print(result.stdout)


if __name__ == "__main__":
    main()

