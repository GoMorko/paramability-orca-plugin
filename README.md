# Paramability for OrcaSlicer

A plugin for OrcaSlicer 2.5 or newer. It adds a **Paramability** tab to OrcaSlicer, next to Prepare and Preview.
In this tab, you prepare your models with [Paramability](https://paramability.app) and do not leave the slicer.

## What is Paramability

Paramability is a free app that prepares models for 3D printing. It works on the files that you already print:
STL, 3MF, OBJ, STEP and more. You do not need CAD software or CAD knowledge.

With Paramability in your slicer, you can:

- **Make a model adjustable.** Give a downloaded STL or 3MF sizes that you can change in a simple form: for
  example the width of a box, the height of a lid or the size of a hole. Then export a new file that is ready
  to print. Other people can open your adjustable model and set the sizes for their own print.
- **Change the sizes of a Fusion design without Fusion.** The Paramability export add-in for Autodesk Fusion
  sends a design together with its user parameters. In Paramability, each parameter is a size in the form.
  Change the sizes and print, with no CAD software open.
- **Cut a large model into parts that fit your bed.** Select your printer size, and Paramability splits the
  model. Add connectors to join the parts after printing: dovetails, pegs, holes for rods or holes for magnets.
- **Make parts fit together**, with press fits and the correct clearances for threads.
- **Change a mesh into a STEP file** that you can edit in CAD software. This works best on mechanical parts,
  such as brackets and enclosures. Sculpts and organic shapes stay mostly as triangles.
- **Pose figurines and miniatures** before you print them.
- **Arrange several models** and export them as 3MF, STL or STEP.

Paramability runs on your computer. It does not send your files to a server, and you do not need an account.

OrcaSlicer is a trademark of its owners. Autodesk and Fusion are trademarks of Autodesk, Inc. Paramability is not
affiliated with the OrcaSlicer project or with Autodesk.

## What the plugin does

- Shows the Paramability app in its own OrcaSlicer tab.
- Saves the files that you export in the tab (3MF, STL, STEP and more) to a folder on your computer. By default,
  this folder is `Downloads/Paramability`.
- Opens help pages and other links in your normal browser, so that the app stays in the tab.

The plugin cannot put a file on the plate directly. OrcaSlicer does not let plugins do this. After an export, use
**File > Import** in OrcaSlicer to add the file to the plate.

## Install

1. Download this repository (Code > Download ZIP) and unzip it.
2. Close OrcaSlicer.
3. Copy the `paramability` folder into the `orca_plugins` folder of OrcaSlicer:
   - macOS: `~/Library/Application Support/OrcaSlicer/orca_plugins/`
   - Windows: `%APPDATA%\OrcaSlicer\orca_plugins\`
   - Linux: `~/.config/OrcaSlicer/orca_plugins/`

   If the `orca_plugins` folder does not exist, make it. Copy only the `paramability` folder, not the full
   repository.
4. Start OrcaSlicer. Open **File > Plugins** and turn on **Paramability**.
5. OrcaSlicer asks if the plugin can use the save folder. Click **Yes**.

## Use

1. Click the **Paramability** tab.
2. Open or make a project in the app, and export a file.
3. A message in the app shows the name of the saved file.
4. In OrcaSlicer, click **File > Import** and select the file.

The first time that you click a link in the app, OrcaSlicer asks if the plugin can start a program. This program
opens the link in your browser. Click **Yes**. If you click No, the app shows the link so that you can copy it.

If you cannot see the tab, go to OrcaSlicer's **Preferences** and increase **Visible plugin pages**.

## Settings

In **File > Plugins**, select Paramability and open its **Config** tab. You can change the save folder and the
largest file size. `docs/how-it-works.md` gives all settings and limits.

## More information

| Document | Contents |
| --- | --- |
| `docs/how-it-works.md` | Settings, what the plugin does with files and links, limits |
| `docs/protocol.md` | The messages between the app and the plugin |
| `docs/development.md` | Tests, and how to try changes |

## Licence

This plugin is free software under the GNU General Public License, version 3 (`LICENSE`). It comes with no
warranty: it is provided "as is". The licence covers this plugin only, not the Paramability app.
