# acc_race_control

If you have organized at least one race with live stewarding, you would know that checking the whole pack of cars to look for incidents is not easy. In endurance races, it's easier because each team has at least one driver who can report directly to the Race Control, but that's not the case for single-driver races. Indeed, they can't drive and report accidents at the same time.
That's why I built an automatic incident reporting system for ACC which detects every contact, the lap in which it happened and the cars involved.

![accidents](https://user-images.githubusercontent.com/26928792/117217921-89343600-ae02-11eb-845d-506cfa57044d.png)

Moreover, you can select a penalty as showed

![penalty](https://user-images.githubusercontent.com/26928792/117217924-89343600-ae02-11eb-88e9-70fda09abf8f.png)

and also get the admin commands to assign that penalty.

![suggestion](https://user-images.githubusercontent.com/26928792/117217926-89cccc80-ae02-11eb-9c9f-ebb7687e65bf.png)

Also, the VSC (virtual safety car) tab allows you to choose a speed limit and get the amount of time each driver is driving over the limit, to punish those who don't comply to VSC rules.

![vsc](https://user-images.githubusercontent.com/26928792/117217929-89cccc80-ae02-11eb-9a8c-1a63885275cb.png)

How to use it

- Default ports are 9000 and 9003, the first one is the broadcast port of the game (info <a href=https://www.assettocorsa.net/forum/index.php?threads/lets-talk-about-broadcasting-users-thread.53828/>here</a>) but can be edited from the ***consts.json*** file;
- Start an ACC session (offline or online);
- Double click on ***acc_race_control.py***;
- Wait for the "Connected" status in the top-right corner;
- In the Accidents tab, the lap number is that associated with the first of the listed cars.


<b>IMPORTANT</b>: sometimes ACC logs may be inconsistent so accidents with only one car may be showed or more than two accidents may be grouped. In the first case, if the car to penalize is not in the list, just type in its number. In the second case you would need to look at the given lap for all the listed cars. Sorry for that, there's no other way to group cars other than by timestamp for now.

Feel free to post a pull request if you have a better way to manage things (and also improve the UI, since I'm not expert in GUI programming or frontend coding) or open an issue to report bugs.
