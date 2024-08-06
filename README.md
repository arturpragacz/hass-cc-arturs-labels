# Artur's Labels

This custom component for Home Assistant expands the use of Labels in the system. The goal is for it to become the one, customizable, powerful system for all the grouping and targeting of entities that a user might ever need.

As the name implies I made it primarily for my own usage. Since I put in all that work though, I thought it might be useful to some other people as well, so I decided to share it here.

## Disclaimer

Right now this is a very early beta release. You might encounter bugs, performance issues and other suboptimal behaviour. Do not even think of installing this without proper backups in place. Due to the nature of the system, this component has to integrate very deeply with Home Assistant internals, making it uniquely susceptible to breakage. This means you have to be very careful with updates, always have a backup ready just in case.

Because of this early beta state some changes in configuration options and system behaviour might be required in the future. Make sure to always read the release notes and make the necessary adjustments.

## What does it do?

Currently the primary functionality of this component is to make it possible for labels to form hierarchies. Any label can become a child of any other label. This means that an entity that is assigned a child label by the user, will be assigned every parent label automatically by the system.

## Start guide

To use this component, follow the below steps.

Before doing anything, read the entire README first.

### Create labels

First create all the labels you might need, using the normal UI interface of Home Assistant.

As an example, let's use the following labels:

- Home
- Ground floor
- First floor
- Kitchen
- Pantry
- Living Room
- TV Area
- Bedroom 1
- Bedroom 2
- Office
- Desk Area
- Stairs
- Low light rooms

These are just area-related labels. You might also consider making more functional labels, like:

- Sensors
- Battery devices
- Important Battery devices
- Motion sensors
- Security motion sensors
- Water pumps
- Critical

Off course there are many other possibilities. The whole point of the system is that it is extremely flexible and can therefore fit a large group of diverse use cases.

### Get the label ids

Once you have your labels created, you need to get their `label_id`s. The easiest way is to go to the templates section in the developer tools and use the code:

```jinja
{% for lbl in labels() -%}
{{ lbl }}: {{ label_name(lbl) }}
{% endfor %}
```

Make sure to copy the result and store it safely.

### Create label relations

In order to create relations between labels, you need to designate parents of every label. For identifying each label, you use its `label_id`. As an example, you put the following in your `configuration.yaml` file:

```yaml
arturs_labels:
  early_loader_hook: true
  labels:
    ground_floor:
      parents:
        - home
    pantry:
      parents:
        - ground_floor
        - low_light_rooms
    living_room:
      parents:
        - ground_floor
    tv_area:
      parents:
        - living_room
    first_floor:
      parents:
        - home
    stairs:
      parents:
        - ground_floor
        - first_floor
    office:
      parents:
        - first_floor
        - low_light_rooms
    # all the other area-related labels...
    battery_devices:
      parents:
        - sensors
    important_battery_devices:
      parents:
        - battery_devices
        - critical
    motion_sensors:
      parents:
        - sensors
    security_motion_sensors:
      parents:
        - motion_sensors
        - critical
    water_pumps:
      parents:
        - critical

```

Each time you make changes to the configuration, you have to restart Home Assistant.

### Install prerequisites

Make sure to install [Early Loader](https://github.com/arturpragacz/hass-cc-early-loader) before installing this component.

### Install the component

This component can be installed using [HACS](https://hacs.xyz/).

- Add a new custom repository to HACS (in the three dot menu).
- Insert the link to this repository.
- Select `integration`.
- Click the add button.
- The integration should now display in HACS.
- Install it like every other HACS integration.
- Restart Home Assistant.

### Assign the labels

After restarting Home Assistant make sure that everything works correctly. If it does, you can now assign labels to your entities, if you didn't do it previously.

One unfortunate limitation of the Home Assistant frontend is that it does not distinguish between assigned and effective labels. For this reason special virtual `assign:` labels are created. In order to change the entity labels, you change only those special labels, everything else will be applied automatically each time you save your changes.

## Usage

### Service actions

You can target labels in your services. By targeting a parent label, you will automatically target all the entities of the child labels as well.

### Devices

You can assign labels not only to entities, but also to devices. Every label, that you assign to a device, will be acquired by all its entities automatically.

### Templates

The template `label_entities(label_name_or_id)` will allow you to get all the entities, for which the specified label is the effective label. The same is true for `label_devices(label_name_or_id)` with respect to devices. On the other hand `labels(entity_id)` will return only directly assigned labels to a given entity.

### Areas

This extensive labeling system is meant to effective replace the need for areas. For this reason areas will be completely **disabled**. You will not be able to target an area in service actions or templates.

### Voice assistants

Because voice assistants rely on areas, they will not function correctly with respect to those. This applies to both Home Assistant built-in voice functionality, as well as external systems. This is a limitation that I plan to address in the future.

## Support

If you want to support this project, then the best way to do it currently is to install it and report any bugs that you encounter.
