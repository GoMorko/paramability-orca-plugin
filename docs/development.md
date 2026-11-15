# Development

## Tests

The tests run the plugin against a fake `orca` module, so OrcaSlicer is not needed. They use only the Python
standard library. From the repository root:

```sh
python3 -m unittest
```

The tests are outside the `paramability` folder on purpose: OrcaSlicer refuses a plugin folder with more than one
`.py` file.

## Try a change in OrcaSlicer

Use a separate settings folder, so that your normal OrcaSlicer settings do not change:

```sh
mkdir -p ~/.orca-dev/orca_plugins/paramability
cp paramability/paramability.py paramability/paramability.svg ~/.orca-dev/orca_plugins/paramability/
/Applications/OrcaSlicer.app/Contents/MacOS/OrcaSlicer --datadir ~/.orca-dev
```

- Copy only the `.py` and `.svg` files. A `__pycache__` folder from the tests is not needed.
- OrcaSlicer reads the plugin when it starts. After a change, copy the file again and restart OrcaSlicer.
- To use a local copy of the app, set `url` in the plugin's Config tab, for example `http://localhost:5173/`.
- Python errors go to `log/python_*.log` in the settings folder.

## OrcaSlicer facts that shape the code

- `get_ui()` returns one HTML string. OrcaSlicer loads it with its own base address, so the page goes to the app
  address at once.
- `on_message()` runs on the main thread of OrcaSlicer.
- OrcaSlicer asks the person before a plugin creates a folder, renames or deletes a file, or starts a program,
  and refuses these when they do not run on the main thread. So the plugin writes files under their final name,
  never renames or deletes, and makes the save folder only when it is missing.
- OrcaSlicer's plugin API is new and can change between versions.
