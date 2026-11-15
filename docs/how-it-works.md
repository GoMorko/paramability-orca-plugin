# How it works

The plugin is one Python file (`paramability/paramability.py`) and a tab icon. It needs no extra Python packages.
OrcaSlicer runs it in its own Python. It registers one "Pages" capability: a tab that shows a web page.

## Settings

Open **File > Plugins**, select Paramability, then the **Config** tab.

| Setting | Default | Meaning |
| --- | --- | --- |
| `url` | `https://paramability.app/?host=orcaslicer` | The page the tab opens. Only http and https addresses are used. |
| `save_folder` | `~/Downloads/Paramability` | Where exports are saved. The plugin makes the folder when it is missing. |
| `max_file_mb` | `512` | The largest file the plugin accepts, in MB. At most twice this size can be in transfer at the same time. |

Changes apply to the next page load or the next saved file.

- When the plugin loads, OrcaSlicer asks one time for the default save folder. For a different folder,
  OrcaSlicer asks the first time a file is saved there.
- OrcaSlicer refuses folders that have a part named like "config", "secret" or "cert" in their path.

## Files

- The app sends each export to the plugin in parts of up to 1 MiB. The plugin writes each part to disk at once,
  so it keeps only one part in memory.
- File names from the app are cleaned: no folders, no unusual or invisible characters, at most 150 bytes.
- Only these file types are saved: 3mf, stl, stp, step, zip, png, gif, mp4, webm, scad, py, txt, json.
- The plugin never overwrites a file. If the name exists, the new file gets a number, for example `part (2).3mf`.
- The plugin refuses a file that is too large, of a different type, or sent while it is busy. It then makes no
  file.
- If a transfer stops halfway, the plugin stops it and empties the file. The empty file stays in the folder, and
  you can delete it. The plugin never deletes files, because OrcaSlicer asks the person before each delete.
- After each file, the app shows a message: the file name when the save worked, or the reason when it failed.

## Links

OrcaSlicer opens every new window inside the tab, which would replace the app. So the app sends links to the
plugin, and the plugin opens them in your browser.

- Only plain http and https addresses are opened, at most one each second.
- The first time, OrcaSlicer asks if the plugin can start a program (the system command that opens an
  address). If you click No, the app shows the link for you to copy.

## Limits

- The plugin cannot put a file on the plate, open files for the app, or read your printer profiles. OrcaSlicer
  gives plugins no way to do this.
- The plugin writes on the main thread of OrcaSlicer, so OrcaSlicer pauses for a moment for each part of a file.
- OrcaSlicer adds its own styles to each page in a plugin tab. The Paramability app removes them when it starts,
  so that it looks the same as in a browser.
- The plugin permissions of OrcaSlicer are not a sandbox. Install plugins only from sources that you trust.
