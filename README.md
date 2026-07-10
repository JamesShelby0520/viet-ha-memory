# Viet Ha Memory Website

一个给 Viet Ha 的照片相册网站。项目支持两种模式：

- GitHub Pages 公开访问：发布网页程序和背景音频，不上传私人照片。访客打开网址后手动选择本地照片文件夹，照片只在当前浏览器本机读取。
- Python 本地动态访问：在电脑上指定一个照片目录，服务启动后自动扫描该目录下的所有图片。

## 本地动态运行

```powershell
python app.py --photo-dir "D:\VietHaPhotos"
```

默认访问：

```text
http://localhost:4173
```

也可以使用环境变量：

```powershell
$env:VIET_HA_PHOTO_DIR="D:\VietHaPhotos"
python app.py
```

## 支持的照片格式

```text
.jpg .jpeg .png .webp .bmp .gif .avif
```

照片会递归扫描，数量不限，按文件修改时间优先展示。页面使用原图地址，不生成压缩图。

## 文案接口

页面默认不显示照片文案，但每张照片数据仍保留 `desc` 字段。需要预留文案时，编辑：

```text
app/static/data/captions.json
```

格式：

```json
{
  "photo-name.jpg": {
    "zh": "中文文案",
    "vi": "Vietnamese caption"
  }
}
```

## 静态导出到 GitHub Pages

默认导出不会包含 `photos` 目录，但会保留 `audio` 目录：

```powershell
python export_static.py
```

导出结果：

```text
docs
```

GitHub Pages 发布 `docs` 目录即可。公开网页会提供本地文件夹选择按钮，不会读取固定本地路径，也不会上传照片。

## 如果必须自动读取固定路径

浏览器网页不能静默读取访客电脑上的固定路径。必须使用 Python 本地服务、桌面应用，或带登录权限的私有后端。
