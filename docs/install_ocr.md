### 安装 TesserOCR
```bash
conda install -c conda-forge tesserocr tesseract
```

### 验证安装
```bash
tesseract --version
tesseract --list-langs #这个命令会输出语言包安装路径，如/home/chris/miniconda3/envs/cube/share/tessdata/
# 根据语言包输出路径，设置环境变量
# 在.env中修改
TESSDATA_PREFIX=/home/chris/miniconda3/envs/cube/share/tessdata/
# 根据输出的语言包路径，修改python代码中的tesserocr.PyTessBaseAPI(path=)参数，例如：/home/chris/miniconda3/envs/cube/share/tessdata/
python -c "import tesserocr; api = tesserocr.PyTessBaseAPI(path='/home/chris/miniconda3/envs/cube/share/tessdata/'); print('支持的语言:', api.GetAvailableLanguages()); api.End()"

# 支持的语言: ['afr', 'amh', 'ara', 'asm', 'aze', 'aze_cyrl', 'bel', 'ben', 'bod', 'bos', 'bre', 'bul', 'cat', 'ceb', 'ces', 'chi_sim', 'chi_sim_vert', 'chi_tra', 'chi_tra_vert', 'chr', 'cos', 'cym', 'dan', 'deu', 'div', 'dzo', 'ell', 'eng', 'enm', 'epo', 'equ', 'est', 'eus', 'fao', 'fas', 'fil', 'fin', 'fra', 'frk', 'frm', 'fry', 'gla', 'gle', 'glg', 'grc', 'guj', 'hat', 'heb', 'hin', 'hrv', 'hun', 'hye', 'iku', 'ind', 'isl', 'ita', 'ita_old', 'jav', 'jpn', 'jpn_vert', 'kan', 'kat', 'kat_old', 'kaz', 'khm', 'kir', 'kmr', 'kor', 'kor_vert', 'lao', 'lat', 'lav', 'lit', 'ltz', 'mal', 'mar', 'mkd', 'mlt', 'mon', 'mri', 'msa', 'mya', 'nep', 'nld', 'nor', 'oci', 'ori', 'osd', 'pan', 'pol', 'por', 'pus', 'que', 'ron', 'rus', 'san', 'sin', 'slk', 'slv', 'snd', 'spa', 'spa_old', 'sqi', 'srp', 'srp_latn', 'sun', 'swa', 'swe', 'syr', 'tam', 'tat', 'tel', 'tgk', 'tha', 'tir', 'ton', 'tur', 'uig', 'ukr', 'urd', 'uzb', 'uzb_cyrl', 'vie', 'yid', 'yor']
```