Layer | Rhino 3-D modeling

[Skip To Main Content](#)

Account

Settings

---

Logout

* placeholder

Account

Settings

---

Logout

Filter: 

* All Files

Submit Search

# Layer

| Toolbar | Menu |
| --- | --- |
| [Layer](../toolbarmap/layer_toolbar.htm)  [Standard](../toolbarmap/standard_toolbar.htm) | Edit  Layers > Edit Layers  Window  Panels > Layers |

The Layer command manages layer properties.

Layers are a way of organizing objects so you can manipulate them all at once or keep track of them in some way. When objects are on a layer, you can turn them all off at once, change their [wireframe](../options/view_displaymode_options.htm#Wireframe) display color, and select them all with one selection.

![](../image/icons/tablayers.png)Layers Panel

![](../image/icons/gear.png "Panel options")[Container options](../toolbarsandmenus/customize_containers.htm)

The Layers panel displays the layers in the model.

When a layout view is involved, an extended set of columns displays.

When linked blocks or worksessions are involved, layers from those external files are displayed in a tree format under the block name.

The layer panel gives you tools for managing the layers in your model.

The Layers pop-up menu gives you access to common layer settings: on/off, locked/unlocked, color, and current status.

#### To display a shortcut window

* [Click](../popup_actions/mouse_buttons.htm) the [Layer pane](../user_interface/rhino_window.htm#Layer_pane) in the status bar.

  The layer pop-up gives you access to a shortcut list of layer options. Right-click in the layer pop-up, to show the context menu.

  Context menu

  ##### Select Objects

  Selects all objects on the layer. Objects on the sub-layers are excluded.

  ##### Change Object Layer

  Moves selected objects to the layer.

  ##### Copy Objects to Layer

  Copies selected objects to the layer.

#### Note

* If no objects are selected, selecting a layer from the status bar layer pop-up window sets the selected layer as the current layer.
* If objects are selected, selecting a layer from the status bar layer pop-up window changes the objects to the selected layer. The current layer is not changed.
* The status bar [Layer pane](../user_interface/rhino_window.htm#Layer_pane) shows the current layer unless objects are selected. When objects are selected, the status bar [Layer pane](../user_interface/rhino_window.htm#Layer_pane) shows the layer of select objects or "varies" if objects fell on more than one layer.

#### To open the Layers panel

* [Right-click](../popup_actions/mouse_buttons.htm) the [Layer pane](../user_interface/rhino_window.htm#Layer_pane) in the status bar.   
  Or
* On the Window > Panels menu, enable Layers.

#### Layer Properties

##### Name

Layer name.

See: [Naming conventions in Rhino](../information/namingconventions.htm)

##### Current

A check and shading indicates current layer.

##### On / Off

Controls global visibility of a layer in model, layout, and detail views at the same time unless the layer is specifically turned off by the [Model On, Layout On, or Detail On](#ModelOn) settings.

##### Lock / Unlock

Controls the selectable state of the objects on a layer.

State of child layers

* If the parent layer gets turned off or locked, the "half lite" light bulb ![](../image/icons/halfoff.png) or lock ![](../image/icons/halflock.png) icon indicates that the child layers will be controlled by the parent layer.
* If the light bulb or lock is all grayed out ![](../image/icons/layeroff.png)![](../image/icons/layerlock.png), then the child layer has it own control, and will not change with the parent layer.
* Child layers cannot be turned on or unlocked on their own when their parent layer is turned off or locked.

##### Color

The default screen display color for objects on this layer.

##### Material

The [material](materials.htm) used for rendering.

The circular icon shows the material thumbnail.![](../image/general/new8.png)

[RenderAssignMaterialToLayer](renderassignmaterialtolayer.htm)

##### Linetype

The linetype assigned to the layer.

##### Print Color

The color assigned to the layer for printing only.

##### Print Width

Opens the Select Print Width dialog. Specify a line width assigned to the layer for printing only or specify No Print if you do not want the layer to print.

#### Define your own line widths

* Add line width values to the printwidths.txt file in the Rhino support folder:

  %AppData%\McNeel\Rhinoceros\<Version>\Localization\<Language>\Support\

In the printwidths.txt file:

* Lines begin with ; or // will be ignored.
* Line width values have to be larger than 0.

#### To change a setting for multiple layers

1. Select a layer.
2. Use Ctrl(CMD)+click or Shift+click to select more layers.
3. Click the light bulb to turn on/off the selected layers all at once.

   This action works with other layer settings.

##### Section Style

Sets how to fill clipping sections of objects on the layer.

* Colors of section styles override print colors.

##### None

Do not fill clipping sections with a hatch pattern.

##### Custom

Fills clipping sections with the hatch pattern selected in the [Section Style](../popup_moreinformation/sectionstyle.htm) dialog.

##### 

##### New Detail On

Controls the default state of the Detail On setting in new detail views.

##### Model On / Layout On / Detail On

Controls visibility of a layer in Model, Layout, and Detail views separately when the [global visibility](#On) setting is turned on.

##### Layout / Detail Color

The default screen display color for objects on this layer in a layout or detail.

##### Layout / Detail Print Color

The color assigned to the layout or detail layer for printing only.

##### Layout / Detail Print Width

The line width assigned to the layer for printing only. Specify a line width assigned to the layer for printing only or specify No Print if you do not want the layer or detail to print. Change the properties of individual objects with the [Properties](properties.htm) command.

## Layer Toolbar options

##### New Layer

Click to create a new layer with [the color for new layers](../options/appearance_colors.htm#New).

##### New Layer with random color

Right-click to create a new layer with a random color.

#### Tab and Insert keys

While editing a layer name, pressing Tab or Insert![](../image/general/new8.png) accepts the name editing and creates a new layer. This makes creating multiple layers more easily.

##### New Sublayer

Click to create a new layer subordinate to the selected layer with [the color for new layers](../options/appearance_colors.htm#New).

##### New Sublayer with random color

Right-click to create a new layer subordinate to the selected layer with a random color.

* Layers can be dragged under other layers to make them sub-layers.
* Layer names on the same level must be unique.

##### Delete

If a layer you want to delete has objects on it, a warning dialog appears.

By default, pressing the keyboard Delete key in the Layers panel deletes selected objects in the viewport, not the selected layers. To enable layer deletion, change EnableLayersPanelDeleteKey to true in [Advanced settings](../options/advanced.htm).![](../image/general/new8.png)

##### Change Object Layer

Moves selected objects to the selected layer.

##### Copy Objects to Layer

Copies selected objects to the selected layer.

#### Steps

1. Select an object.
2. Select the target layer.
3. Left-click or right-click the button.

See: [ChangeLayer](#ChangeLayer).

##### Move Up

Move the selected layers up in the list.

##### Move Down

Move the selected layers down in the list.

##### Move Up One Parent

Moves the selected layer up one level in the layer tree structure.

##### Filters

When a model has a large number of layers, the list of layers may be difficult to manage. Layer filters let you adjust the visibility of the layers in the panel.

#### Layer Filter Options

##### All Layers

##### On Layers

##### Off Layers

##### Locked Layers

##### Unlocked Layers

##### Layers with Objects

##### Empty Layers

##### Selected Layers

* Click a checkbox to enable or disable the filter.
* Right-click a checkbox to enable the filter and disable all others.![](../image/general/new8.png)

##### Columns

Shows the column header list to show or hide layer settings.

Right-clicking a column header shows the same list.

##### Tools

##### Layer State Manager

Opens the [Layer States](layerstatemanager.htm) panel.

##### Select All

Select all layers currently displayed in the list.

##### Select Object Layer

Selects the layers of the currently selected objects.

* The [HighlightObjectLayers](highlightobjectlayers.htm) command provides the same functionality.![](../image/general/new8.png)

##### Invert Selection

Inverts the selection state. All selected layers are unselected and all unselected layers are selected.

##### Select Objects

Select objects for on the currently selected layer.

##### Select Sublayer Objects

Selects object on the currently selected layer and its sub-layers.

##### Change Object Layer

Change selected objects to selected layer.

See: [ChangeLayer](#ChangeLayer).

##### Copy Objects to Layer

Copy selected objects to selected layer.

##### All Layers On

Turn on all hidden layers.

##### Expand All

Show all child layers.

##### Collapse All

Hide all child layers.

##### Columns

Select which columns to display in the Layer panel.

##### Column Sort

Allows layers to be sorted by columns. Clear the check to prevent layers from being sorted by accident.

##### Search

Enter text to only list the layers with the text in their names.

Wildcard characters can be used to match patterns:

\* = Match zero or more characters  
? = Exactly one character

#### Layer list options

#### To sort the list

* Click a column header.

  Layer names are sorted in Natural sort order.![](../image/general/new8.png)

  Natural sort order: 1, 2, 3, 10 (10 is listed after 3)

  Alphabetical sort order: 1, 10, 2, 3 (10 is listed before 2)

#### To hide or show columns

* [Right-click](../popup_actions/mouse_buttons.htm) the column heading, and check or clear the column name.

#### To change a column width

* Drag the column heading dividers.

#### To edit a layer's properties

* [Right-click](../popup_actions/mouse_buttons.htm) the layer name and select an option from the context menu, or select an option from the Layer Toolbar.

#### To select layers

* Click and drag the cursor over a list of layers to select them.
* Hold [Shift](../popup_actions/shift-key.htm "Shift key") to select a group of adjacent layer names.
* Hold [Ctrl](../popup_actions/ctrl_key.htm "On a Mac, use the Command ⌘ key") to select multiple individual layer names.
* To quickly select all but a few layers, Select all layers, de-select a smaller set of layers.

#### Layer context menu options

#### To open the layer context menu

* [Right-click](../popup_actions/mouse_buttons.htm) on a layer column.

  The context menu may display different items when you right-click on different column.

##### Worksession Reference (Worksession layers only)

For more information, see [Worksession](worksession.htm).

##### Set Active Model

The selected model is open for editing.

The current model closes and becomes an attached model. You are prompted to save changes in the currently active model.

##### Detach Model

Removes the external file from the worksession list.

##### Update Model

Refreshes the selected attached files.

##### Attach Model

Attaches an external file to the worksession list.

##### Restore Default

Resets the column being right-clicked to the default setting.

##### Random Color (Model view Color column only)

Assigns random colors to selected layers.

##### Layer Off in Selected Details Only (Layout On column only)

##### > This Layout

Turns the layer off in the selected detail view, and on in all other detail views in the current layout.

##### > All Layouts

Turns the layer off in the selected detail view, and on in all other detail views in all layouts.

##### Layer On in Selected Details Only (Layout On column only)

##### > This Layout

Turns the layer on in the selected detail view, and off in all other detail views in the current layout.

##### > All Layouts

Turns the layer on in the selected detail view, and off in all other detail views in all layouts.

##### Layer Off in this Detail Only (Detail On column only)

##### > This Layout

Turns the layer off in the active detail view, and on in all other detail views in the current layout.

##### > All Layouts

Turns the layer off in the active detail view, and on in all other detail views in all layouts.

##### Layer On in this Detail Only (Detail On column only)

##### > This Layout

Turns the layer on in the active detail view, and off in all other detail views in the current layout.

##### > All Layouts

Turns the layer on in the active detail view, and off in all other detail views in all layouts.

##### Select Objects

Selects objects on the selected layers.

##### Select Sublayer Objects

Selects objects on the sub-layers of the selected layer.

##### Change Object Layer

Selects objects in the model to change to selected layer.

##### Copy Objects to Layer

Selects objects to copy to selected layer.

##### New Layer

Creates a new layer.

##### New Sublayer

Creates a new sublayer.

##### Duplicate Layer

Copies the layer with its attributes.

##### Duplicate Layer and Objects

Copies the layer with its attributes and all of the objects on the layer.

See: [DupLayer](duplayer.htm).

##### One Layer On

Sets the selected layer on and turns all others off.

See: [OneLayerOn](onelayeron.htm).

##### Match Properties

Select a layer to match.

See: [MatchProperties](matchproperties.htm).

##### Delete

Deletes the selected layers.

##### Rename

Edits the name of the selected layer.

##### Expand Sublayers

Expands the layer tree of the selected parent layer.

##### Collapse Sublayers

Collapses the layer tree of the selected parent layer.

### Layer Keyboard Shortcuts

#### Standard list control shortcuts

|  |  |
| --- | --- |
| ▲ | Moves the selection up. |
| ▼ | Moves the selection down. |
| PageUp | Moves the selection a page up. |
| PageDown | Moves the selection a page down. |
| Home | Moves the selection to the first item. |
| End | Moves the selection to the last item. |
| [Ctrl](../popup_actions/ctrl_key.htm "On a Mac, use the Command ⌘ key") | Adds individual layer to the selection. |
| [Shift](../popup_actions/shift-key.htm "Shift key") | Adds a range of layers to the selection. |

#### Layer-specific shortcuts

The Layer panel must have focus (cursor over the Layer panel) for these shortcuts to work.

|  |  |
| --- | --- |
| F2 | Renames the selected layer. |
| F5 | Refresh the layer list. |
| Insert | Creates a new layer below the selected layer. |
| + | Expands the selected layer. |
| [Ctrl](../popup_actions/ctrl_key.htm "On a Mac, use the Command ⌘ key") or  [Shift](../popup_actions/shift-key.htm "Shift key") +  Number pad + | Expands all child layers of the selected layer. |
| - | Collapses the selected layer. |
| [Ctrl](../popup_actions/ctrl_key.htm "On a Mac, use the Command ⌘ key") or [Shift](../popup_actions/shift-key.htm "Shift key") +  Number pad - | Collapses all child layers of the selected layer. |

#### Column options

##### Displays/hides columns in the layer dialog

Name

Current

On

Lock

Color

Material

Linetype

Print Color

Print Width

When Layout views exist, additional options appear:

Layout On

Layout Color

Layout Print Color

Layout Print Width

When Detail views exist, additional options appear:

Detail On

Detail Color

Detail Print Color

Detail Print Width

# Related commands

# ChangeLayer

| Toolbar | Menu |
| --- | --- |
| [Layer](../toolbarmap/layer_toolbar.htm) | Edit  Layers >  Change Object Layer |

The ChangeLayer command changes the layer of selected objects.

#### Steps

1. [Select](../popup_actions/select_objects.htm) the objects.
2. Select the layer name from the list.

Layer for Objects options

#### Available layers

##### Name

Layer names.

* Double-click a layer name to set the target layer and close the dialog box.

##### Set layer current

Sets the target layer current.

##### Select

Select an object in the viewport to specify the layer.

##### New

Creates a new layer.

# ChangeToCurrentLayer

| Toolbar | Menu | Panels |
| --- | --- | --- |
| [Layer](../toolbarmap/layer_toolbar.htm) | Edit  Layers >  Change Object to Current Layer | Layer  [Right-click](../popup_actions/right-mouse_click.htm) layer name >  Change Object Layer |

The ChangeToCurrentLayer command changes the layer of selected objects to the current layer.

#### Steps

* [Select](../popup_actions/select_objects.htm) objects.

# CopyToLayer

| Toolbar | Menu |
| --- | --- |
| [Layer](../toolbarmap/layer_toolbar.htm) | Edit  Layers >  Copy Objects to Layer |

The CopyToLayer command copies selected objects to a specified layer.

#### Steps

1. [Select](../popup_actions/select_objects.htm) objects.
2. Select the layer name from the list.

Layer to copy objects

#### Available layers

##### Name

Layer names.

* Double-click a layer name to set the target layer and close the dialog box.

##### Set layer current

Sets the target layer current.

##### Select

Select an object in the viewport to specify the layer.

##### New

Creates a new layer.

#### To access hidden command-line options

* Type a hyphen in front of the command name: -CopyToLayer.

| Command-line options | |
| --- | --- |
| NewLayer | Create a new layer. |
| SelectObject | Select an object to specify the layer. |
| SetCurrent | Yes/No |

# HighlightObjectLayers

| Toolbar | Menu |
| --- | --- |
| [Layer](../toolbarmap/layer_toolbar.htm)  [New in V8](../toolbarmap/new_in_v8_toolbar.htm) | Edit  Layers > Highlight Object Layers |

The HighlightObjectLayers command selects the layers of selected objects when the Layer panel is visible.

![](../image/topic_illustrations/highlightobjectlayers.gif)

* The same functionality can be accessed from Layers panel > Tools ![](../image/icons/tools.png)> [Select Object Layer](#Select_Object_Layer).

# LayerStateManager

| Toolbar | Menu |
| --- | --- |
| [Layer](../toolbarmap/layer_toolbar.htm) | Edit  Layers > Layer State Manager  Window  Panels > Layer States |

The LayerStateManager command can:

* Save the current state of layers.
* Restore the previously saved state of layers.
* Import the layer state list from a .3dm file.

#### Steps

1. Set up your layers.   
   The Layer State Manager saves the current layer settings.
2. In the Layer State Manager panel, click Save, and then type a name for the configuration.

![](../image/icons/tablayerstates.png)Layer States Panel

![](../image/icons/gear.png "Panel options")[Container options](../toolbarsandmenus/customize_containers.htm)

#### Toolbar buttons

##### Save

Saves a new layer state.

* Click the "Name" column head to toggle the list between ascending and descending orders.

See: [Naming conventions in Rhino](../information/namingconventions.htm)

##### Restore

Reverts to the specified layer state.

##### Delete

Deletes the selected layer state.

##### Import

Imports the layer state list from a .3dm file.

##### Search box

Enter text to only list the layer states with the text in their names.

#### Right-click context menu

##### Restore

Reverts to the specified layer state.

##### Delete

Deletes the selected layer state.

##### Rename

Edit the name of the selected layer state.

##### Save

Saves a new layer state.

##### Update

Overwrites the selected layer state with the current layer setup.

#### Layer settings to restore

Restores the state of layers in the model space.

|  |  |
| --- | --- |
| [Current](#Current)[On / Off](#On)[Locked / Unlocked](#Lock)[Color](#DisplayColor)[Material](#Material)[Expanded](#Expand) | [Linetype](#Linetype)[Print color](#PrintColor)[Print width](#PrintWidth)[Section Style](#SectionStyle)[New Detail On](#NewDetailOn) |

#### Layout or Detail Layer setting to restore

Restores the state of layers in layout or detail.

|  |  |
| --- | --- |
| [[On / Off](#On)](#Current)[Color](#DisplayColor) | [[Print color](#PrintColor)](#Linetype)[Print width](#PrintWidth) |

* When you save a layer state in a layout viewport and no detail view is active, the layout’s layer properties are saved.
* Layouts and detail views share the same layer properties in a layer state. Their layer properties can be restored to the active detail view or multiple selected detail views. If no detail view is currently active or selected, the layer properties are restored to the current layout.
* If a layer state is saved in a model viewport, restoring the layer state to a layout or a detail view applies global layer properties to the layout/detail view layer properties.

# OneLayerOn

| Toolbar | Menu |
| --- | --- |
| [Layer](../toolbarmap/layer_toolbar.htm) | Edit  Layers >  One Layer On |

The OneLayerOn command turns a specified layer on and all other layers off.

#### Steps

1. Make a model viewport active.
2. [Select](../popup_actions/select_objects.htm) the layer to turn on from the list.

   Or click the Select button to select an object on the target layer.

# OneLayerOff

| Toolbar | Menu |
| --- | --- |
| [Layer](../toolbarmap/layer_toolbar.htm) | Edit  Layers >  One Layer Off |

The OneLayerOff command turns off the selected object's layer.

#### Steps

* [Select](../popup_actions/select_objects.htm) an object on the layer in a model viewport.

# RenderAssignMaterialToLayer

| Toolbar | Menu |
| --- | --- |
| [Not on toolbars.](../popup_moreinformation/toolbarwhattodo.htm) | [Not on menus.](../popup_moreinformation/menuwhattodo.htm) |

The RenderAssignMaterialToLayer command assigns a material to a layer from the command-line.

#### Steps

1. Select a material by entering its name or ID.
2. Select a layer by entering its name or ID.

## See also

![](../image/command_icons/_no_toolbar_button.png)

##### [RenderAssignMaterialToLayersOfObjects](renderassignmaterialtolayersofobjects.htm)

Assigns a material to the selected object's layer from the command-line.

![](../image/command_icons/_no_toolbar_button.png)

##### [RenderAssignMaterialToObjects](renderassignmaterialtoobjects.htm)

Assigns a material to the selected objects from the command-line.

# RenderAssignMaterialToLayersOfObjects

| Toolbar | Menu |
| --- | --- |
| [Not on toolbars.](../popup_moreinformation/toolbarwhattodo.htm) | [Not on menus.](../popup_moreinformation/menuwhattodo.htm) |

The RenderAssignMaterialToLayersOfObjects command assigns a material to the selected object's layer from the command-line.

#### Steps

1. Select a material by entering its name or ID.
2. Select one or more objects.

## See also

![](../image/command_icons/_no_toolbar_button.png)

##### [RenderAssignMaterialToLayer](renderassignmaterialtolayer.htm)

Assigns a material to a layer from the command-line.

![](../image/command_icons/_no_toolbar_button.png)

##### [RenderAssignMaterialToObjects](renderassignmaterialtoobjects.htm)

Assigns a material to the selected objects from the command-line.

# SetLayerToObject

| Toolbar | Menu |
| --- | --- |
| [Layer](../toolbarmap/layer_toolbar.htm) | Edit  Layers >  Set Current Layer to Object |

The SetLayerToObject command makes the layer of a selected object the current layer.

#### Steps

* [Select](../popup_actions/select_objects.htm) an object on the layer you want to be current.

## See also

![](../image/command_icons/_no_toolbar_button.png)

##### [Snapshots](snapshots.htm)

The Snapshots command saves and restores [Named Views](namedview.htm), [Named Positions](namedposition.htm), [Layer States](layerstatemanager.htm), as well as [rendering settings](../documentproperties/render.htm), object settings including [locked](lock.htm)/[hidden](hide.htm) state, [display mode](setobjectdisplaymode.htm), [material](../properties/material.htm), [position](namedposition.htm), [light settings](../documentproperties/render.htm), [curve piping](../properties/curvepiping.htm), [displacement](../properties/displacement.htm), [edge softening](../properties/edgesoftening.htm), [shutlining](../properties/shutlining.htm), and [thickening](../properties/thickening.htm).

[Copy and duplicate objects](../seealso/sak_copyandduplicate.htm)

[Use layers](../seealso/sak_layer.htm)

[Work with blocks, groups, and worksessions](../seealso/sak_blocksgroups.htm)

[Scripting layers](../information/rhinoscripting.htm#LayerSublayer)

[McNeel Wiki: Imported and linked block layer names](http://wiki.mcneel.com/rhino/rhinov5status_layernames#examplelinked_block_layer_names)

Rhinoceros 8 © 2010-2026 Robert McNeel & Associates. 04-Nov-2026
