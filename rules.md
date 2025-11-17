
 PDF To Markdown Converter
Debug View
Result View
Rules for Spoils of Empire: a Strategy Fantasy PBEM Game
The Wayback Machine - https://web.archive.org/web/20010307180419/http://www.srv.net:80/~ram/soe_ru...

Rules for:
Spoils of Empire
A fantasy, strategy game designed for play-by-email (PBEM)
by Rick Morneau
ram@axxess.net
http://www.axxess.net/~ram
Copyright © 2001 by Richard A. Morneau,
all rights reserved.
INTRODUCTION [ Table of Contents ]

Until recently, the entire globe groaned under the iron-fisted rule of the old empire. But the empire is now
dead and new bases of power are forming. You can become one of the them, or you can stand by and watch
others fight for dominance. The choice is yours.

Spoils of Empire is an open-ended, computer-moderated, strategy, fantasy, role-playing game designed for
play-by-email. The setting is similar to that of Ancient Rome, but with one major difference: magic is both
real and powerful.

You will start the game with a small amount of gold which you can use to obtain an education, hire followers,
and purchase any items that you need to create and define your starting characters. From then on, you can
interact with the characters of other players in whatever way you choose. You can attempt to increase your
power at the expense of others, or just wander around the world and involve yourself in whatever fashion
suits you.

GAME TIMING [ Table of Contents ]

Spoils of Empire is designed to be an asynchronous game, which means that there is no need for a fixed turn
time. When your orders are processed, they are simply placed on a queue and executed when the appropriate
amount of game time has passed. For example, if you order one of your characters to travel to another
location, then you may see on your report that he has departed but has not yet arrived. You will be notified of
his actual arrival in a later report. It is even possible for you to cancel an order in progress and any that were
queued but not yet started and provide new ones to be carried out instead.

Since the game is asynchronous, there is no need for a fixed turn time, and the Gamemaster can process your
orders as often as he wants. It's also possible for the Gamemaster to set up a server on his computer to
process each order as soon as it arrives. This, of course, will depend on the Gamemaster and his computer
and Internet resources.

However, if the Gamemaster does process orders on a regular basis (i.e., if there is a fixed turn time), then the
computer will take advantage of this and will process more of your orders (rather than just queue them for
later processing). In effect, the game will be run synchronously, rather than asynchronously.

If you provide more than one order for a character, then the orders will be executed in sequence. Thus, if you
wish, you can provide several days worth of orders in advance. This is especially useful if you have to be
away from your computer for a while.

The Gamemaster can also define the game-to-real-time ratio. The default is 7, which means that one real day
equals one game week.

It is recommended that the Gamemaster process orders at least once per real day. In general, status reports
will only be mailed to players if they supplied new orders or if something important happened to their
characters since the last time orders were processed.

THE COMMAND LANGUAGE [ Table of Contents ]

The command language of Spoils of Empire is intended to be easy-to-learn and as English-like as practical.
Here are some examples:

Promote Bill Jenkins to Captain.
Assign 20 soldiers and 23 horses to Bill Jenkins, and have him go to
Riverton and attack Mike May.

Words in the command language are not case sensitive. Thus, Have , have , and HAVE are the same, as well as
John Parker , johN parKER , or JOHN PARker. The spelling of character names that appear in your status
reports will be the same as what you provided when you first named the character.

Commas, colons, and semi-colons are always ignored and may be included for readability.

Periods are also ignored unless an error occurs during parsing. When this happens, the computer will try to
recover by ignoring all input until the next period. Thus, it's very important to end each sentence with a
period, otherwise other unrelated orders will be ignored if an error occurs.

Any punctuation always terminates the item it follows. Because of this, make sure not to use punctuation in
names. For example, if you name a character James T. Kirk , the computer will assume that the name is just
James T and that Kirk is a completely separate name.

Spaces and tabs are treated as word separators, but are otherwise ignored.

You may use as many lines as necessary for commands. The end of a line means nothing to the parser. Here's
an example:

Assign 20 soldiers and 2 workers and 200 gold and 22 horses
to Bill Gershwin.
Have him go to Riverton, and say "Here is the money
I promised you." to King Bodo Bunji, and give him 100 gold.

Titles are ignored except in the NAME and PROMOTE commands, where they are mandatory. For example,
Have Captain Jane Tucker go to Riverton is the same as Have Jane Tucker go to Riverton. In general, it is
a good idea to not use titles in your orders (except, of course, in the NAME and PROMOTE commands). If
you accidentally mis-spell the title, then the computer will consider it part of the name and the order will fail.

Anything that appears within double quotes is a literal message and is treated as a single item. Make sure
that the message itself does not contain any double quotes. For example, the following will cause errors when
it is parsed:

Tell Baroness Judicia "As you requested, I told the King "The
secret password is MOONSHINE", but he never replied".

Instead, use single quotes within a message, like this:

Tell Baroness Judicia "As you requested, I told the King 'The
secret password is MOONSHINE', but he never replied".

Messages can be up to 2500 bytes in length (about 1 full page of dense print). Any excess will be truncated.

If a number sign (i.e. '#') appears anywhere outside of a message, then it and everything to the right of it up to
the end of the line will be ignored. Thus, number signs may be used to add comments to your orders which

will be ignored by the computer. Here's an example:

Promote Bill Jones to Captain # When he gets there, I'll have him
and have him go to Riverton. # lead the attack on Genghis Khan.

Make sure you don't include comments inside a message! Here's an example:

Have Captain Pierce tell King Bodo Bunji
"I promise not to attack you again. # Like hell!
In fact, as a token of my good will, # Hahahaha!
I'll give you 10000 gold the next time # I'll skewer you later!
we meet."

In the above example, King Bodo Bunji will receive everything that appears between the double quotes,
including your comments.

Except for the contents of messages and comments, everything in your orders to the computer should be
spelled correctly. The computer will be able to detect and correct many spelling errors, but not all. It's a good
idea not to depend on this feature.

One exception to the spelling rule is that plural 's' may be added to the names of items and ranks where it
makes sense, but an error will never occur if it is used incorrectly. For example, 10 soldier means the same as
10 soldiers and 1 horses means the same as 1 horse.

CHARACTER TYPES AND NAMES [ Table of Contents ]

There are two types of character in Spoils of Empire: unnamed characters and named characters. Unnamed
characters have at most a single major skill at skill level 1, and are always referred to by the lowest rank
associated with that skill. There are two of these classes: soldier (skill=combat) and sailor (skill=sailing).

Here is an example:

Assign Bishop Sami Lukasa and Simon Peres and 200 soldiers and 5
saliors to John Parker, and have him go to Riverton and capture
Mike May.

In the above example, 200 soldiers and 5 sailors are unnamed characters. The soldiers each have skill level 1
in combat, and the sailors each have skill level 1 in sailing. The three named characters are John Parker,
Bishop Sami Lukasa, and Simon Peres.

In addition, there is one more class of character known simply as worker. These characters have no special
skills whatsoever, and can only work at common labor or under the supervision of a more skilled person.

Unnamed characters can not be trained beyond their basic skill. If you wish to train an unnamed character,
you must first give him or her a name, as in the following example:

Name female soldier Nancy Benton and have John Parker teach her
combat for 3 weeks.

In the above example, one of your soldiers is singled out with the name Nancy Benton and is given additional
combat training. From that point on, she will not be counted with the unnamed soldiers but will be listed
separately, and she will only take orders that are explicitly addressed to her or to someone to whom she is
assigned.

Any unnamed character (including workers) may be given a name and additional training.

In this game, every name must be unique. This means that if another player is already using a name, then you
may not also use it. Since you may not know if a particular name is already in use, the computer will generate
a unique random name for your character if you should accidentally try to use an existing name. To prevent
this from happening, always try to make your names as original as possible. Once a character has been given
a name (even a random one), it may not be changed.

There is no limit to the number of named characters that you can have. However, named characters command
much higher salaries than unnamed characters because they have greater responsibilities. See the PAY
command for more information about salaries.

SKILLS [ Table of Contents ]

As mentioned above, unnamed characters have only a single skill at a skill level of 1 (except for workers,
who have no skills at all). They have a skill level of zero in all other skills. A named character, however, can
have several skills at values ranging from 0 to 100. Here is the complete list of skills that characters can
learn:

Combat, Sailing, Magic, Religion, Engineering,
Mining, and Trading.

There are four ways that a character may increase his ability in a skill:

By going to a school; see the STUDY command for more details.
By being taught by another character that you control; see the TEACH command for more
details.
By experience gained from actually using a skill.
By possessing a magical amulet that provides knowledge of a particular skill.
By divine intervention; see the PRAY command for more details.
Whenever a character applys a skill, his skill level will affect how successful he is. It is also possible that he
can learn from experience (whether he succeeds or fails at applying the skill). If so, his skill level will go up
automatically.

Whether or not a character uses a skill and which skill he uses depends on what he is doing. Many activities,
such as walking, speaking, and performing manual labor do not require a skill. Other activities, such as
buying and selling, do not require a skill, but having an appropriate skill can improve the outcome. For
example, if you have skill in trading, then you will be able to buy items at a discount and sell them at a profit.
There are also tasks which cannot be performed at all without the necessary skill. For example, you cannot
cast a spell if you know nothing about magic.

A character's health can also affect his ability to use a skill. If the health value is less than 100, then the
effective skill value will be reduced proportionately. For example, a magic user with a magic level of 72 and
a health of 65 may not cast a spell that requires a magic skill level of more than 65% of 72 = 46, or more than
46 points of magic power.

Additional details about skills and about how they can be applied will be discussed in the appropriate context.
For example, the use of the trading skill will be discussed in the sections that describe the BUY and SELL
commands.

DEATH [ Table of Contents ]

Named characters have a health value which can range from 0 to 100. A value of 100 indicates perfect health
and is not shown on status reports. A value of 0 means that the character is dead. Anything less than 100 will
be indicated on status reports. Health can become less than 100 if the character is wounded in combat,
punished by the gods, and so on. Health of less than 100 is automatically regained at the rate of one point per
game day.

A dead character can be resurrected only by intervention of the gods. (See the description of the PRAY
command for more information about this.) However, there is a time limit after which resurrection is no
longer possible. The time limit is a number of game days equal to the sum of all skill levels. For example, a
character with a combat skill level of 17 and a trading skill level of 6 may be resurrected up to 23 days after
death. At the end of the 23 days, resurrection will no longer be possible. (In fact, after 23 days the computer
won't even remember the name of the dead character.) Also, during this time, one skill will be chosen
randomly each day and its value will decrease by 1 point. Thus, a dead character will gradually lose his skills.

DEAD LEADERS [ Table of Contents ]

Every player has a lead character, and this person is referred to simply as your leader or lead character.
Throughout these rules, when I say you I am generally referring to this character. In other words, think of this
character as yourself.

If your lead character dies and is not resurrected in time, the game ends for you, the player. You can, of
course, start over again with a new leader. If you do rejoin the game, you should choose different names for
your leader and subordinates.

MAGIC [ Table of Contents ]

Characters with skill in magic have the power to cast magical spells. They can summon exotic creatures,
teleport people and goods over long distances, and so on.

Anyone with a magic skill level greater than zero has access to a quantity of magical power equal to the skill
level. For example, a person with a magic skill level of 37 may control up to 37 points of magical power.
This power is expended whenever a spell is cast.

Expended magical power is regained at the rate of 1 point of power per game day.

The amount of power needed to cast a spell depends on the nature of the spell. For example, summoning a
dragon will require more power than summoning a griffin. Refer to descriptions of the appropriate
commands, such as SUMMON, TELEPORT, and so on for details.

The amount of time needed to cast a spell generally depends on the amount of power required. The amount of
time needed for the actual execution of the spell will depend on the spell. For example, teleporting people
and summoning magical creatures is instantaneous, while flying depends on the speed that the spell-caster
can provide.

Magic is useless in combat because spell-casting requires both time and uninterrupted concentration, which is
impossible to achieve during the noise and confusion of a battle. For this reason, magic users are essentially
useless in battle unless they also have skill in combat or have control of powerful magical creatures (see the
SUMMON command).

Finally, magic users like to cast spells using their own power and magic skill, because they can learn by
doing so. If you have a magic user continually charge magic items, rather than cast his own spells, he's likely
to get bored and leave your service. Keep this in mind.

RELIGION [ Table of Contents ]

A person with religion skill may beseech his god for miracles. However, unlike magic, which always works if
the skill and power are available, miracles depend on the whims of fickle gods, and may not work.

A person with religion skill has a bank of power that he may use to pay his god for his requests. The
maximum number of points of power that may be accumulated is equal to the person's religion skill level.
When a god takes power from a supplicant, it will be regained automatically at the rate of one point per day.

When a person requests a miracle, the probability of success will be equal to the amount of religious power
that he currently has. For example, if the supplicant has a religion skill level of 72 and a current religious
power level of 55, then there is a 55% chance that the god will grant the miracle.

If a god takes power from the supplicant, he will always do so before deciding whether or not to grant the
miracle. Thus, it is possible for power to be taken even though no miracle is granted.

If a supplicant requests a miracle but has no available religious power, then the god may become angry and
may punish the supplicant.

The actual miracles that may be requested are described in the appropriate sections below. (See the BLESS,
CURSE, and PRAY commands).

Characters with religion skill may also try to collect tithes and donations. See the PREACH command for
more information.

COMMUNICATIONS [ Table of Contents ]

Communications in Spoils of Empire is essentially instant and is achieved by the use of magic. Also,
communication magic is readily available and cheap.

Because of this, it is generally possible for a leader to give orders to his subordinates and receive reports from
them at almost any time, even if neither communicant has any magic skill, since the world is full of non-
player mages willing to send messages for a few pennies. It is also possible to send messages to other
players, and even to broadcast a message that will be instantly received by everyone on the planet (See the
SAY/TELL command for further details about magical communication).

Finally, since information can be transmitted so easily and cheaply, knowledge of distant events is generally
available. Because of this, when major events do occur, whether they involve you or not, you will be told
about them as soon as they happen.

MAP LOCATIONS [ Table of Contents ]

Commands that refer to locations may use any names on the map that have dots. All of these locations are
either human-populated towns or uninhabited ruins infested with monsters. Commands may not refer to
locations that do not have an accompanying dot, such as the names of islands, lakes, deserts, and so on.

There are three possible positions that a character can be in relative to a location: inside , outside , or near.

The default is to be inside a location. For example:

Have Kathy Lincoln go to Kitesta.

The computer will assume that you want Kathy to go to Kitesta and enter the city.

If you want a character to go to a location but to remain just outside the gates or town limits, then use the
word outside :

Sail to outside Madegi Doy.

If you want a character to go to a location but to remain well outside the gates or town limits, then use the
word near :

Teleport Joe Flint to near Agriponga.

A character that is inside a location will be able to detect and report on many of the people that are also inside
the same location as well as all the people that are outside the same location. People inside a location,
however, will not be able to see people that are near the location.

A character that is outside a location will be able to detect and report on only the people that are also outside
the same location. He will not be able to see people that are inside or near the location (except for the person
that has secured the location, if any).

A character that is near a location is assumed to be hiding or trying to remain undetected by blending into the
countryside in the vicinity of a town or city. Thus, he will be able to detect and report on only the people that
are also near the same location as well as people that are outside the location. He will not be able to see
people that are inside the location. However, since he is assumed to be trying to avoid detection, and has
plenty of room to do so, the chance of being seen by other people near the same location is very slim.

MAGICAL ITEMS [ Table of Contents ]

In Spoils of Empire, there are several types of especially powerful magical items that characters may be able
to acquire.

These magical items were all created by a single, powerful enchantress, so long ago that even her name is no
longer remembered, nor is the secret of how to make them. All of these items are indestructible, and some of
them have been found. But the historical records show that many more were created that have not yet been
found.

The enchantress gave each of these items a name, and should you ever possess one, you must use that name
when referring to it. For example, if you possess a magical amulet named Wameka and you wish to give it
to Joe Flint, then you should give the order Give Wameka to Joe Flint. Note that these names always start
and end with an "*" to emphasize their uniqueness and to ensure that they do not conflict with human names.

The records show that there are five kinds of magic item. Here is a description of each kind:

AMULET - A magical amulet provides knowledge of a skill up to a specified level. In
your reports, an amulet will be listed by its name followed by the skill and level in
parentheses; e.g. *Wameka* [amulet, trading 72]. Anyone wearing such an amulet will be
able to buy and sell items as if he were a trader with a trading skill level of 72. If
a person possesses more than one amulet for the same skill, then the highest level will
apply. An amulet NEVER provides skill in magic or religion. You may not TEACH knowledge
provided by an amulet.
CRYSTAL - A magical crystal may be used to store magic power. In your reports, a
crystal will be listed by its name followed by the amount of power stored in it; e.g.
*Nashi* [crystal, power 51/60] , indicating that the crystal contains 51 points of
available power and may store up to a maximum of 60 points. The power in a crystal is
always tapped before the natural power of the spell-caster. Thus, if you don't want to
use the power in a crystal, then give it temporarily to another person. A crystal does
not increase an ability in a skill. For example, if you try to teleport a total
encumbrance of 50 and your magic skill level is only 45, then even a crystal with 5 or
more points of power will not allow success. However, you can split the group into
smaller groups and teleport them separately. A crystal gains one point of power every
day that the possessor is at his natural maximum. In other words, any power that the
possessor cannot add to his natural power will instead go into the crystal (up to its
maximum, of course). The possessor must have a magic skill level of at least 1 to be
able to charge a crystal. Power in a crystal is not lost when the crystal is given to
another person. Thus, one person may charge a crystal that can then be used by another
person. If a person possesses more than one crystal, then their combined power will be
available for use. When this occurs, one will be completely drained of power before the
next one is tapped, and there is no way to predict which one will be tapped first. A
crystal can not store religious power.
ORB - A magical orb allows the owner to obtain a report of who is at a distant
location. The result is similar to having a subordinate at the location give a report,
but without the need for a subordinate at the location. In effect, an orb is a crystal
ball or palantir. An orb provides its own power, and one point of power is expended for
each ten miles of distance between the user of the orb and the location being scanned.
Expended power is regained automatically at the rate of one point per day. There is no
maximum to the amount of power an orb may hold. An orb can only detect humans. It can
not detect monsters. See the SCAN command for further details.
RING - A magical ring provides protection to the owner in combat. In reports, a ring
will be listed by its name followed by the protection factor; e.g. *Fidula* [ring, prot
3] , which indicates that the probability of being hit or captured in combat will be
reduced by a factor of 3. For example, if you are wearing *Fidula* and someone attacks
you with a hit chance of 74%, then the actual chance will be reduced to 24% (drop
fractions). If a person possesses more than one ring, then the most powerful one will
be effective. If a person with a ring is also BLESSED, then the blessing will
effectively add +1 to the ring's protection factor.
WAND - A magical wand provides the ability and power to use a specific magic spell. In
reports, a wand will be listed by its name followed by the spell, current power level,
and magic skill level; e.g. *Opistama* [wand, teleport 62/75] , which indicates that the
possessor may cast teleport spells up to a total power of 62. It also indicates that
the wand can store up to 75 points of power. Power that is expended will be
automatically regenerated at the rate of one point per day. A wand provides both the
necessary magic skill and power. Thus, it may be used by someone who has no skill in
magic at all. To use a wand, the person that possesses it should be given the spell-
casting order exactly as if he were casting the spell with his own skill and power
followed by the word with or using and the name of the wand; e.g. Summon 3 dragons with
*Agamonke* or Have McCoy teleport me to Kitesta using *Opistama*. A wand will never be
used automatically - its name must be specified in the order.
There are two ways of obtaining magical items. You can SEARCH uninhabited ruins with the hope of finding
one, or you can attempt to temporarily CONJURE a particular type of magic item. Items that are found by
searching will last forever. Conjured items, however, remain only for a limited time before automatically
returning to wherever they came from.

If a magical item is only temporary, the number of days remaining will be shown on your status reports; e.g.
Opistama [wand, teleport 62/75, 3d] , which indicates that the wand will remain for at least three more
days. If the time remaining is shown as 0d , then the item has less than 1 day left.

Crystals, orbs, and wands may also be charged by directly transferring power from a magic-user to the item
by means of the CHARGE/RECHARGE command. Power may also be transferred from the item to a magic-
user using the ABSORB command.

Magical items will never work together to perform the same task. For example, a wand will not tap a crystal
if it needs power - it can only use its own power.

MAGIC-FREE ZONES [ Table of Contents ]

There are locations on the map that are marked as being "magic-free". In these locations, magical power does
not exist, either in people or in magical items, making it impossible to cast a magic spell.

If a person enters a magic-free zone, then all of his magic power will be instantly drained away. The same
applies to any magic items that store power. Other magic items (rings and amulets) will not be affected since
they do not use magic power in the same way. Summoned creatures are also not affected when they enter a
magic-free zone, since they don't store magic power.

After leaving a magic-free zone and entering a normal area, any magic power that was lost when entering the
zone will not be restored. However, magic power will begin to accumulate in the usual way (1 point per day).

A person may enter a magic-free location by means of a magic spell (FLY, TELEPORT), but, obviously, may
not leave it in the same way.

PLAYER IDS [ Table of Contents ]

Each player has a unique, randomly generated identification number. Here is an example from a status report:

End-of-turn summary for P158, leader General Mike Anderson:

The above indicates that the player's unique ID is 158.

Whenever a character takes part in a major battle ON THE SIDE OF THE ATTACKERS , he will become
a "public figure", and his player ID will be displayed with his name in all status reports of all players from
that point on. Here are two examples:

Mother Betty Salerno (F, preaching)
Captain Tom Watson (P17, M, recruiting soldiers)

Betty Salerno has never been on the attacking side of a major battle, so her player is not known. However,
Tom Watson has been part of an attack force in a major battle and so is now a public figure and, in effect,

"wears the colors" of whoever controls him. If he is assigned to another player, he will automatically display
the ID of the new player.

In addition, the player ID of an attacker will always be displayed at the battle itself, whether major or not, to
those who take part in or observe the battle.

The purpose of the IDs is to make it easier to keep track of the various factions that important characters
belong to.

THE "HAVE" COMMAND AND THE CONJUNCTION "AND" [ Table of Contents ]

By default, all commands apply to your lead character; i.e., the character that you should think of as
representing yourself. If you want one of your subordinates to do something, then you must use the HAVE
command. In the following examples, we will assume that your leader is named Bill Jones:

Have Jim Thomas go to Emerald City.
Go to Riverton. # Bill Jones will go to Riverton.

In the first example, your subordinate Jim Thomas will depart for Emerald City. In the second example, your
leader Bill Jones (i.e. you ) will depart for Riverton. In other words, the following two orders will accomplish
exactly the same thing:

Go to Riverton.

or

Have Bill Jones go to Riverton.

If you want orders to be obeyed sequentially, you can use the conjunction and. Here is an example:

Have Jim Thomas go to Riverton and give 100 gold to
King Bodo Bunji.

In the above example, Jim Thomas will go to Riverton. As soon as he arrives, he will give 100 gold to King
Bodo Bunji.

However, while it does save typing, use of and is optional, because multiple orders to the same person will be
executed in sequence. For example:

Have Jim Thomas go to Riverton.
Have Jim Thomas buy 20 horses.
Have Jim Thomas go to Ocean City.

is exactly the same as:

Have Jim Thomas go to Riverton and buy 20 horses
and go to Ocean City.

The HAVE command must always be followed by the name of one or more persons. For example, the
following command will fail:

WRONG : Have 10 soldiers go to Riverton.

If you want unnamed characters to GO somewhere, you must first ASSIGN them to a named character and
give the order to the named character. Here is a correct example:

Assign 10 soldiers to Joe Smith and have him
go to Riverton. # The 10 soldiers will go with Joe.

If more than one name is specified, then the conjunction and must appear between each one. When this
occurs, the result will be exactly the same as if you had given identical orders to each person individually.
Here is an example:

Have Joe Flint and Mike Morrison and Sandy Tyler go to Umadosh
and buy 10 horses.

The above is identical to the following:

Have Joe Flint go to Umadosh and buy 10 horses.
Have Mike Morrison go to Umadosh and buy 10 horses.
Have Sandy Tyler go to Umadosh and buy 10 horses.

In other words, they will each go to Umadosh independently, and each one will purchase 10 horses
independently. If you want them to travel together and have just one of them purchase the horses, then do it
like this:

Assign Mike Morrison and Sandy Tyler to Joe Flint.
Have him go to Umadosh and buy 10 horses.

Mike and Sandy will travel with Joe, but only Joe
will buy and pay for the horses.
Your leader is not the only character that can give orders to subordinates. It's also possible for a subordinate
to give an order to another subordinate. Here is an example:

Have Jim Thomas go to Tashendi
and give 50 gold to Fenderman,
and have him go to Riverton
and buy 5 horses and go to Emerald City.

In the above example, Fenderman will depart for Riverton only after Jim Thomas has arrived in Tashendi and
given him the 50 gold. Note, though, that Fenderman has now replaced Jim Thomas as the recipient of any
additional orders following and. Thus, in the above example, it is Fenderman that will buy the 5 horses after
he arrives in Riverton. And after he purchases the horses, he will depart for Emerald City. If you want Jim
Thomas to buy the horses in Tashendi and then go to Emerald City, then do it this way:

Have Jim Thomas go to Tashendi
and give 50 gold to Fenderman
and have him go to Riverton.
Have Jim Thomas buy 5 horses and go to Emerald City.

In the above example, Fenderman will go to Riverton, and Jim Thomas will buy 5 horses in Tashendi before
continuing on to Emerald City.

It takes no time to issue a HAVE order (although, of course, it will take time for the subordinate to carry it
out).

In a synchronous game, some orders may take more than one turn to execute. For example, if you give
yourself or a subordinate an order to go to a distant location, the trip may take more than one turn. Because of
this, if you give additional orders before the completion of any previous orders, then the new orders will be
carried out only after the old ones have completed. If you want to cancel orders-in-progress either for
yourself or for a subordinate, use the HALT command. For example, if Jim Thomas was on his way to
Emerald City at the end of the last turn, and you want him to stop what he was doing and instead go back to
Riverton, then issue the following order:

Have Jim Thomas immediately halt and go to Riverton.

The HALT command will cancel all pending orders.

As stated above, orders are always executed in sequence. Keep this in mind when combining orders to
yourself with orders to others. For example:

(1) Go to Riverton.
Have Jim Thomas go to Emerald City.

is not the same as:

(2) Have Jim Thomas go to Emerald City.
Go to Riverton.

In (1), you will not give the order to Jim Thomas until after you arrive in Riverton. In (2), you will give the
order to Jim Thomas before you depart for Riverton.

There is a potential problem when you give yourself an order between two orders to the same subordinate.
Here is an example:

Have Jim Thomas recruit 100 soldiers.
Go to Riverton.
Have Jim Thomas buy 2 armor.

In the above example, you are asking Jim Thomas to buy the armor after you arrive in Riverton. However, if
he has not yet finished recruiting the soldiers, should he stop recruiting and buy the armor or should he finish
recruiting and then buy the armor? In a case like this, the computer will have him finish recruiting and then
buy the armor. If this ends up taking longer than you anticipated, you can cancel the order with one of the
HALT/STOP commands.

The conjunction and may also be used to link the people and/or items that are mentioned in a command, as
long as it makes sense and is not ambiguous. Here are some examples:

Promote Joe Bellows and Jane Smith to Captain.
Assign 2 workers and 20 soldiers and 50 gold to Major Willy Benton.

However, you may not use and to link items after the preposition to because the result will be ambiguous.
Here are some examples of incorrect and correct orders:

WRONG: Promote Joe Bellows and Jane Smith to Captain and Major.
RIGHT: Promote Joe Bellows to Captain and Jane Smith to Major.

In other words, you must explicitly tell the computer
the title that applies to each person.
WRONG: Assign 20 soldiers to Willy Benton and Jim Thomas.
RIGHT: Assign 14 soldiers to Willy Benton and 6 soldiers
to Jim Thomas.

In other words, you must explicitly tell the computer
how many soldiers are being assigned to each person.
You can always use and to link items after to if there is no possibility of confusion:

Have Jim Thomas go to Riverton and Jamestown.
Have Jim Thomas go to Riverton and to Jamestown.
Have Jim Thomas go to Riverton and go to Jamestown.
Have Jim Thomas go to Riverton. Have Jim Thomas go to Jamestown.

In all four of the above examples, Jim Thomas will first go to Riverton and then immediately depart for
Jamestown.

THE ADVERB "THEN" [ Table of Contents ]

You may use the adverb then anywhere in your orders to make them more readable. It is always ignored by
the computer. Here are some examples:

Go to Kitesta and recruit 100 soldiers and 5 workers, and buy
100 horses. Then go to Kobya Tesh.
Have Bligh sail to Kitesta, and then to Vayoni, and then to
Sidnaya, and then have Joe Flint attack Genghis Khan.

GROUPS AND GROUP LEADERS [ Table of Contents ]

As some of the earlier examples imply, it is not necessary for all of your subordinates to remain with you all
of the time. You can create groups of characters and items and have them do different things at different times
and in different locations.

Whenever you use the HAVE command, the character named in the command will automatically become a
group leader if he was not already one. From that point on, he will remain independent unless given specific
orders to join another group. Here are some examples that should illustrate this point:

Recruit 100 soldiers and 2 workers.
Name female soldier Jeanne Dunn and female worker Pindimya.
Promote Jeanne Dunn to captain.
Assign 20 soldiers to Jeane Dunn.
Assign 30 soldiers to Pindimya.

At this point in time, both Jeanne Dunn and Pindimya are still part of your group, since neither has received a
HAVE command.

Go to Riverton.

When the above command is executed, you, Jeanne Dunn, Pindimya, 1 worker, and 99 unnamed soldiers will
all go to Riverton together. There is still only one group, and you are the group leader.

Give Pindimya 10 gold.
Have her study magic for 10 weeks.
Go to Bakersville.

Jeanne Dunn and her 20 soldiers will now go to Bakersville with you, your worker and your 49 soldiers,
while Pindimya and her 30 soldiers will remain in Riverton. Pindimya will immediately search for a teacher
to begin studying magic. Her 30 soldiers will remain with her, but will do nothing else.

In general, when you give a command to a named character, the command will apply to that character plus to
any other characters (named or unnamed) assigned to him. The only exceptions to this are the STUDY,
TEACH, and other commands for which doing so would either not make sense or would not change the
meaning of the command. For example, if you give Pindimya a command to BUY something, she will make
the purchase and her soldiers will simply tag along. However, if you gave her a command to GO somewhere
or BUILD something, then she and her soldiers would GO or BUILD together.

When you give a command to a group leader, make sure that he or she has whatever is needed to carry out
the command. For example, if you had not given Pindimya some gold in the above example, she would not
have been able to study magic because she would not have had any money to pay her teacher.

THE PREPOSITION "TO" [ Table of Contents ]

The English language allows us to use a few verbs with and without the preposition to , with exactly the same
meaning. In the command language, you have the same freedom. In the examples below, each pair of orders
will have exactly the same results:

Have Joe give me 50 gold.
Have Joe give 50 gold to me.

Teach Mike Sanders magic.
Teach magic to Mike Sanders.

Have Bill Smith assign me 10 soldiers and 3 workers.
Have Bill Smith assign 10 soldiers and 3 workers to me.

Offer Wizard Jamomita 100 gold.
Offer 100 gold to Wizard Jamomita.

In other words, if a legitimate command without to is grammatical in English and has exactly the same
meaning as the same command with to , then you may use either one.

PRONOUNS [ Table of Contents ]

The pronouns I , me and you always refers to yourself; i.e. to your lead character. For example, if your lead
character is Billy Jones, then the command Have Joe Flint give me 100 gold or Have Joe Flint give you 100
gold means that you want your subordinate Joe Flint to transfer 100 gold to Billy Jones.

Since me and you mean the same thing to the computer, you can use whichever one sounds best. Here are
some examples:

Go to Madegi Doy and have Joe Flint give you 10 horses.

Joe Flint will give 10 horses to your leader as soon as
your leader arrives in Madegi Doy.
Have Mike Fenton recruit 100 soldiers and come to Madegi Doy and
assign 25 soldiers to me.

Mike Fenton will transfer 25 soldiers to your leader as soon
as he arrives in Madegi Doy.
You may also use the pronouns him and her when there is no chance for ambiguity. Here's an example:

Assign 10 soldiers and Doctor McCoy to Joe Flint and have him
go to Tashendi.

In the above example, him refers to Joe Flint. Thus, Doctor McCoy and 10 soldiers will join the group led by
Joe Flint, and all of them (under the leadership of Joe Flint) will then depart for Tashendi.

The pronouns him or her will always refer to the most recently named person of the proper gender who is not
the agent of the current order and who is not part of a longer list of people and/or items. Thus, him could not
have referred to Doctor McCoy in the above example, both because Joe Flint was more recently named and
also because McCoy is linked to 10 soldiers.

The agent of an order is the name following have (or your lead character if have is not used). Here's an
example:

Have Mark Bolton study combat for 4 weeks.
Have Donald Nap go to Madegi Doy and give him 100 gold.

In the above example, him refers to Mark Bolton, not to Donald Nap, because Donald Nap is the agent of the
current command. In other words, Donald Nap will give the gold to Mark Bolton as soon as Donald Nap
arrives in Madegi Doy.

The pronouns him and her will never refer to your lead character, even if you mention him or her by name.
Here's an example (assume that your lead character is Billy Jones):

Have Joe Flint give 10 horses to Billy Jones and have him go to
Madegi Doy.

In the above example, him refers to Joe Flint.

To prevent confusion and unnecessary mistakes, you should always use the pronoun me or you when
referring to your leader.

The computer knows the gender of each named character. Thus, him can only refer to a male character and
her can only refer to a female character. Here's an example where both are used:

Give 50 gold to Nancy Myers and 20 horses to Bill Fenton
and have her join him.

In the above example, Nancy will become part of Bill's group.

You may also use the pronoun it to refer to the most recently mentioned item or unnamed character. Here are
some examples:

Buy 1 horse and go to Umadosh and give it to Bill May.
Recruit 1 worker and assign it to Joe Flint.
Have Mike Myers buy 1 slave and give it to me.

You may use the pronoun them to refer to the most recently mentioned group or list of people and/or things.
Here are some examples:

Have Mary Anderson recruit 5 soldiers and 3 workers and come to
Tashendi and assign them to me.
Purchase 20 horses and assign them and 2 sailors to Watusingi,
and have him go to Madegi Doy and assign them to Joe Flint.

In the last example above, the first them refers to 20 horses. The second them refers to 20 horses and 2
sailors.

You can even use it and them together:

Buy 1 galley and recruit 40 sailors.
Assign it and them to Popeye The Sailor Man.

However, them can never refer to entities mentioned in separate commands:

Recruit 10 soldiers and buy 10 horses and assign them to
Joe Flint.

In the above example, only the 10 horses will be assigned.

In order to conform with grammatical English, you must use it when referring to more than one unit of
substances (i.e. mass nouns ) such as wood , iron , or armor :

Buy 10 stone and give it to Carl Higgins.
Take 10 copper and 20 silver from Bill Hawthorne, and give it to
Pamadandu.
Give 50 armor to Thomas Ames and have him to go to Kitesta and
give it to Phil Lucas.

However, if you mix mass nouns with other things, then you must use them :

Have Joe Flint buy 10 armor and 10 horses and give them to me.

You may also use the pronoun them to refer to the most recently mentioned group of agents who are not the
agents of the current command. Here is an example:

Have Joe Flint and Mary Wise # They are currently in Umadosh.
tax for 4 weeks.
Go to Umadosh and stop them and assign them to me, and
then go to Tashendi.

In the above example, Joe and Mary will tax the people of Umadosh until you arrive (assuming that you
arrive in less than 4 weeks). As soon as you arrive, they will stop collecting taxes and join you. You will then
immediately depart together for Tashendi.

In summary, the computer will always correctly interpret the pronouns him and her as long as the referent is
not ambiguous, and as long as you do not use them to refer to your leader or to an unnamed character. It is
safest to always use either you or me for your leader. The computer will also correctly interpret them and it ,
as long as you remember to use it for a single unnamed person.

NUMERIC QUANTITIES [ Table of Contents ]

Many commands require you to specify how many items or how many people are involved. These quantities
should be specified exactly as in English. For example, if you want to give 150 gold to John Anderson, then
give the order "Give 150 gold to John Anderson".

Specific quantities should always use digits. For example, use "10" rather than "ten". The parser can
occasionally understand small spelled-out quantities such as "a/an", "one", "two", and "five", but you should
not count on this.

You may also use the quantifier all or every to represent everything in a character's possession, or everything
that is available to the character at the time the order is executed, depending on the context. The words all
and every are synonymous and may be used interchangeably. Use whichever one sounds best to you. You
may also use the optional preposition of , the optional article the and the optional possessive adjectives my ,
your , his or her with all. You may also use all the or all of the where it makes sense. Here are some
examples:

Have Joe Flint go to Kitesta and sell all of his silver
and all his horses.

Try to sell all of the silver and all of the horses that he has.
Go to Tashendi and buy every horse and recruit all the soldiers.

Buy as many horses as are available and that I can afford,
and then try to recruit as many soldiers as are available
and that I can afford.
Offer all of my gold to Wizard Yamana.

Offer her all the gold that I have.
Go to Plugby and buy every gem.

Buy everything that is available or until I run out of
money.
You may also use all of before it and them. Here are some examples:

Gather stone for 3 days and give all of it to Engineer
Tony Bingham.
Have Billy the Kid recruit every soldier and give all of
them to me.

You may also specify a percentage of a character's current inventory by using the percent sign "%" or the
spelled-out word "percent". Here are some examples:

Give 82 percent of my soldiers to Hanna Davis.
Have Joe Barney sell 50% of his horses and then give me all his
gold.
Take 20 percent armor from Gandiluna.
Buy every horse and give 30% of them to Kevin Star.

Note that the word "of", the article "the", and the possessive adjectives "my", "your", "his", and "her" are
optional and may be used to make the sentence more readable. You may also use "it" and "them" as in the last
example.

You can also specify everything except a particular amount by using the words "all but" or "all except":

Go to Kitesta and take all but 50 horses from Joe Flanders.
Have Mindentai sell all except 10 of her gems.
Buy all the wood and give all but 3 of it to Louise Peron.

[Note in the last example, that you must use the pronoun "it" to refer to the wood because "wood" is a mass
noun.]

You may use percentages and "all but" or "all except" only with the following commands:

ASSIGN/GIVE
GET/OBTAIN/TAKE
OFFER

PAY
REPAY
SELL

If you do not specify a quantity where one is normally required, then it will be as if you had specified an
infinite quantity. In other words, the character will keep trying until you give him a HALT/STOP order or
until it becomes impossible to continue. Here is an example:

Teleport to Kitesta and buy horses.
# Keep buying until I'm halted or I run out of money.
Note that any commands that follow a command for an infinite quantity will not execute until it becomes
impossible for the "infinite" order to continue. For example, if the above command had been Teleport to
Kitesta and buy horses and then go to Plugby, then the go order will be executed only after you have run
out of money. As long as you have enough money, you will keep trying to buy horses.

THE PREPOSITION "UNTIL" [ Table of Contents ]

You may use the preposition until followed by a time and date wherever it makes sense. Here are some
examples:

Build weapons until 5:00 March 7 and sell them.
Collect wood until 12:00 May 9, 1150 and go to Kitesta and give it
to Mack Butler.
Have Joe Flint tax until 1:37 Sep 27, and then briefly report and
come to Tashendi.

The time, month, and day must be specified. The year is optional. If the year is not specified, then the current
year is assumed. However, if the resulting date has already passed, then the following year is assumed.

IMPORTANT!
If you specify a time that is more that 10 game years in the future, then the result will be
unpredictable!
In Spoils of Empire, each month has exactly 30 days. Thus, a year has 360 days. This makes until commands
easier to use, and avoids the potential confusion caused by leap years.

You can use either the full name of the month or the 3-letter abbreviation. Minor spelling errors will be
detected if you spell the month out in full. No spelling errors are allowed if you use a 3-letter abbreviation.

When until is used as shown above, the command that is currently executing when the specified time arrives
will finish executing. For example, if you have only partially completed building something, you will finish
building it. If you want to stop at exactly the time specified, then use the adverb exactly :

Build weapons until exactly 5:00 March 7 and sell them.

In the above example, you will stop at exactly the time specified, and any partially completed work will be
lost.

You can even add an until phrase to a WAIT FOR order:

Wait for Joe Flint until exactly 12:00 May 19 and assign him to
me and go to Kitesta.

In the above example, if Joe doesn't arrive by the deadline, then the assignment will fail, and you will go on
to Kitesta without him. If Joe arrives before the deadline, then you will wait until the specified time and then
depart with him. Note also, that you MUST use exactly if until is used with WAIT FOR.

THE ADVERB "REPEATEDLY" [ Table of Contents ]

If you want one or more orders to be repeated over and over again, then use the adverb repeatedly. Here is an
example:

Have Joe Flint tax for 1000 weeks. # Essentially forever.
Repeatedly take all the gold from him and recruit every
soldier and give them to him.

In the above example, you will continuously take whatever gold Joe Flint has collected in taxes and recruit as
many soldiers as possible and assign everyone you recruited to him.

You may terminate a repeat loop by specifying the number of times it should execute:

Have Master Trader Bill Johnson repeatedly buy 10 gems and
definitely sell all his gems 5 times, and then come to
Kitesta and give me all his gold.

In the above example, Bill will buy and sell gems exactly 5 times, and then depart for Kitesta.

You may also use the preposition until to terminate a repeat loop:

Have Mike Ransom repeatedly go to Kitesta and recruit 10 soldiers
and come to Plugby and give them to me until 8:00 Jun 17, 1152,
and then come to Plugby and join me.

In the above example, the repeat loop will halt at the specified time and Mike will then depart for Plugby (if
he was not already there when the loop terminated).

A repeat loop that does not specify a loop count or use until may be canceled only by means of a
HALT/STOP order.

Obviously, it makes no sense to use repeatedly without a loop count or until more than once for the same
character, or to give that character any orders at all after such a repeat order. Here's an example:

Have Mike go into the horse trading business. Since he
is a high level trader, he should make a profit on each
sale.
Have Mike Jones repeatedly buy 100 horses and sell them.
Have Mike Jones go to Madegi Doy.

In the above example, Mike Jones will never depart for Madegi Doy. Instead, he will be in an infinite loop of
buying and selling horses. The computer will reject orders that follow infinite repeat loops.

You may not give the same repeat loop to more than one agent:

WRONG: Have Joe Flint and Phillip Cassidy repeatedly ...whatever...

RIGHT: Have Joe Flint repeatedly ...whatever...
Have Phillip Cassidy repeatedly ...whatever...

Repeat loops should not be nested inside each other. Any nested orders will be executed in sequence as if
they were part of the outermost loop.

THE ADVERB "IMMEDIATELY" [ Table of Contents ]

There will be times when a character is busy performing some task and you need to interrupt him and have
him do something short and simple, but without canceling all of his existing orders. To accomplish this, use
the adverb immediately. Here's an example:

Joe Flint is busy taxing but have him send a message to Larry
Hanks without stopping what he's doing.
Have Joe Flint immediately tell Larry Hanks "Where's the gold you
promised us?".

In the above example, Joe will send the message and continue taxing.

The adverb immediately is especially useful when you grossly underestimate how long it will take for
completion of a GO/COME/MOVE/TRAVEL order because of excess encumbrance. If you want someone to
lighten his load while enroute and arrive more quickly, then use the adverb immediately , as in the following
example:

Joe is lugging 200 stone from Plugby to Kitesta, and at the
rate he's going, he won't arrive for 3 months. Have him dump
the stone and write it off as a loss so that he'll arrive
sooner.
Have Joe Flint immediately discard all his stone.

If a person is moving when an immediately discard order is executed, the arrival time will be recalculated
based on the new encumbrance.

Immediately applies from the point where it appears until the end of the sentence. Thus, there is no need to
repeat it for each command in the sentence.

An order using immediately will be executed immediately after the order it follows, even if that order is for
another character. If the "immediate" order is the very first order in the current set of orders, then it will
execute at the very beginning of order processing (i.e., at the very beginning of the turn).

You may use immediately with any of the following commands:

ASSIGN/GIVE
CREATE
DISCARD/DISMISS/FREE/RELEASE
ENSLAVE
GET/OBTAIN/TAKE
HALT/STOP
INVEST
KILL/EXECUTE
LURK and UNLURK
NAME
PAY
POST
PROMOTE
QUERY and REPORT
REPAY
SAY and TELL
TRANSFER
UNLOAD
UNNAME
If you use immediately with any other commands, it will be ignored. It's use with HALT or STOP has special
meaning and is described in that section of the rules.

THE ADVERBS "QUIETLY" AND "SILENTLY" [ Table of Contents ]

There may be times when your subordinates are doing boring tasks over and over again. Normally,
everything that they do is logged on your status report. Since this can result in excessively long reports, you
may want your subordinates to work silently.

To accomplish this, use either of the adverbs "quietly" or "silently".

"Quietly" will apply only to the single command verb that it precedes.

"Silently" will be in effect from the point where it appears until the end of the sentence. Thus, there is no
need to repeat it for each of the remaining commands in the sentence.

Here are some examples:

Have Joe Flint repeatedly and quietly buy every horse and definitely
sell all his horses.

Silently charge Wadengiti and give it to Alia Mondi and have her
and Merlinus and Andapogi and Bill Johnson and Wendi Morrow and
Harold Abili charge it. Have Alia Mondi summon 2 dragons using
it.

In the first example above, the results of each purchase will not be reported, whereas the results of each sale
will be reported. In the second example, the results of the CHARGE and GIVE commands will not be
reported, but the result of the SUMMON command will be reported.

When "quietly" or "silently" are in effect, even error messages will be suppressed.

These adverbs will have no effect on commands that are intended to provide information, such as REPORT,
INTERROGATE, PROBE, TELL, and SCAN. For example, in:

Have Joe Flint repeatedly and silently buy every horse and
definitely sell all his horses and report.

Joe Flint's report will appear in your status report, even though it follows "silently" in the same sentence.

"IF" STATEMENTS [ Table of Contents ]

You may have characters do things conditionally using the word if. You may also optionally specify an
alternative using either else or otherwise. Here are some examples:

If Joe Flint has at least 100 gold, then take it from him and buy
10 horses; otherwise wait 1 day.
Have Mike Hanson go to Benkamu and if Lorrie Smith has less than
100 workers then have him take all her workers and give her
100 workers. # Make sure Lorrie has at least 100 workers.

Else and otherwise are synonymous and may be used interchangeably. Note that the pronouns "it" and "them"
refer to the actual amounts specified. For example, in the first example above, "take it" means "take 100
gold", regardless of how much gold Joe Flint actually has.

IF statements may NOT be nested!

The available test conditions are:

less than OR fewer than
more than
exactly
at least
at most

If no condition is specified, then it will be equivalent to using exactly :

If Joe Flint has 50 horses, then ... # If he has exactly 50.

You may also use the words any or some :

If I have any gold then give it to Mata hari.

Equivalent to "more than 0 gold".
Any and some are synonymous and may be used interchangeably.

You may specify conditions for any character that you control and for any valid game items (horses,
catapults, galleys, etc.), recruitable ranks (soldiers, sailors, and workers), or summonable creatures
(skeletons, chimeras, demons, etc.).

You may also test for encumbrance, as in the following example:

If Admiral Raja Moja has at most 2000 encumbrance, then have him
sail to Madegi Doy.

Encumbrance checks always include the encumbrance of horses and wagons. Thus, they are mostly useful
for sailing and flying. If you use encumbrance checks for land travel, the result will not be correct if the
group has horses or wagons.

You may also test for magical or religious power, as in the following examples:

If I have at least 25 magic power then teleport to Salem.
Have Primate Melissa Davies repeatedly briefly report and if she has
less than 50 religious power, then have her preach for 1 week;
otherwise have her pray for me.

You may use the modifiers "magic", "magical", "religious", or "religion". If no modifier is given (e.g., "If I
have at least 25 power..."), then the current highest value of the two will be used in the test.

Since there is no equivalent to an "end if", the scope of an IF statement will always end at the end of the
sentence. Consider the following:

Go to Kitesta and if Louise Sanders has any gold then take it from
her and fly to Umadosh.

In the above example, you will only fly to Umadosh if Louise has gold. If you want to fly to Umadosh
regardless, the GO command must not be in the same sentence:

Go to Kitesta and if Louise Sanders has any gold then take it from
her.
Fly to Umadosh.

Make sure that agents are specified correctly in IF commands:

Have Genghis Khan briefly report, and if he has at least 1000
soldiers then go to Kitesta and join Charlemagne.

In the above example you will go to Kitesta if Genghis has at least 1000 soldiers. If you want him to go, then
make sure you give him the GO order:

Have Genghis Khan briefly report, and if he has at least 1000
soldiers then have him go to Kitesta and join Charlemagne.

Note in the above two examples that "briefly report" is being used as a placeholder because it is not possible
for IF to follow the agent's name. For example, we cannot say "Have Genghis Khan if he has ...". There must
be at least one command between the agent's name and the IF statement.

An IF statement that is not part of a "have" clause will always be for you (i.e., the lead character), and the
condition will be tested after all preceding orders for you have executed:

Go to Madegi Doy.
If Malevola has more than 1200 soldiers then have Rufus Dawson take
200 soldiers from her.
Then have him come to Madegi Doy and join me.

In the above example, you will check how many soldiers Malevola has as soon as you arrive in Madegi Doy.
Rufus will then come to Madegi Doy and join you, whether or not he takes the 200 soldiers from her.

QUITTING THE GAME [ Table of Contents ]

If you want to completely eliminate yourself from the game, then UNNAME your lead character. If you wish,
you may then resubmit new character generation orders. However, if you do so, you may not use the same
character names as you used previously! Also, when submitting new character generation orders, please
remember to set your email subject line to "SOE New Player". For more information, see Appendix A:
Character Generation.

COMMAND DESCRIPTIONS [ Table of Contents ]

In the above introduction, we saw examples of some of the commands that may be used in the game. In the
following sections, we will discuss each of the available commands in detail.

The very first order in any set of orders must be a PASSWORD order. All additional orders must follow the
PASSWORD order. The computer will use your password to determine who you are. (The LEADER
command is used only during character generation and should never be used in later turns.)

In general, it's a good idea to end your orders with the command ZZZ. Here's an example:

Password "Gobbledygook Password"
Assign 11 horses and 10 soldiers to Joe Smith
and have him go to Riverton.

... several more orders ...

zzz

The computer will always stop processing your orders when it reaches the end of the file, so ZZZ is not
normally necessary. However, if your mailer attaches a signature or some other non-game material to the end
of your email message, then ZZZ will prevent the computer from trying to make sense of it and printing a lot
of error messages.

ABSORB [ Table of Contents ]

Use the ABSORB command to have a magic-user transfer power from a magical crystal, orb, or wand to
himself. Here are some examples:

Absorb 10 points from Madingo and give it to Joe Flint.
Have Merlinus absorb 22 power from Hasimpa and 10 from Ajimi.
Absorb Kwimikonta and Madingo and 15 from Jupo.

Note that the word points or power after the quantity is optional.

If the quantity is not specified, then the character will transfer as much power as possible from the item to
himself. If you wish, you may also state this explicitly using the words all or everything :

Absorb all power from Gendari and all points from Fiba.
Have Merlinus absorb everything from Umiki.

A character may absorb power from a magical item that is not in his possession as long as the character that
does possess it is in the same location and is controlled by the same player.

Only magic power may be transferred from a magical item. Religious power may not be transferred.

ADDRESS [ Table of Contents ]

Use the ADDRESS command to change your email address. Here is an example:

Address "xyz@boogaloo.gov"

Note that the address must be enclosed in double quotes.

All future reports from the computer or messages from the Gamemaster will be mailed to the new address.

When you first create your character, your email address is set to the email address in your mail header. This
address will remain in effect until you explicitly change it using the ADDRESS command.

ALLY, ENEMY, and NEUTRAL [ Table of Contents ]

Use the ALLY, ENEMY, or NEUTRAL command to declare your attitude towards a particular named
character. Here are some examples:

Ally Joe Flint.
Enemy Bill Fenton and Captain Mike Sanderson.
Neutral Phil Anderson and Genghis Khan and Lord Tamasaki.

Note that these are not normal commands! They take effect as soon as they are parsed, regardless of where
they appear in your orders.

A summary of your current situation will appear at the end of each status report.

If someone who you have declared ALLY is attacked by someone else, your forces at the same location will
automatically aid your ally. The reverse, however, is not true; if you attack someone, your allies at the same
location will not automatically attack with you.

If you encounter an enemy while traveling, then the outcome will be the same as if you had given a
CAUTIOUSLY ATTACK order.

Note that automatic attacks occur only when you meet each other on the road. Attacks will never be
automatic in towns. If you want to attack someone in towns that you are just passing through, then give an
appropriate ATTACK order for each town. Here is an example:

Go to Dairy and attack Genghis Khan and Musakoma,
and then go to Winis and attack Genghis Khan and Musakoma,
and then go to Daft and attack Genghis Khan and Musakoma,
etc.

Note that even an ALLY will not automatically aid you if you attack someone else. Allies will only help if
you are attacked. If you want to help another player's character in an attack, use the SUPPORT command.

Allies are always allowed to enter locations which you have secured. Enemies are never allowed to enter.

ASSIGN and GIVE [ Table of Contents ]

Use the ASSIGN or GIVE command to transfer control of people or things from one named person to another
named person. ASSIGN and GIVE are synonyms and may be used interchangeably. Here are some examples:

Assign Sorcerer Thanatok and Bishop Saramore to Admiral Iko
Nomura.
Have General KT Jones give 200 gold and 1000 horses and 1000
soldiers to Major Bill Smith.
Assign all but 100 of my soldiers to Bill Penny.
Assign Jimiko Tena and 40 sailors and 1 galley to Captain
Haru Pencha.

An attempt to ASSIGN/GIVE will fail if the donor and recipient are in different locations. The order will also
fail if you forget to specify the quantity of unnamed people or items to be assigned. For example, if you say
"Assign soldiers to Bill Penny", the order will fail. You must specify how many soldiers you are assigning.

Unnamed characters and items to be assigned must be under the direct control of the donor. They may not
belong to another character even if that character is part of the donor's group.

After people or items have been assigned to a person, they will remain with that person until reassigned,
killed, discarded, or destroyed. If a person who is assigned has other people or items assigned to him, then
they will remain assigned to him. Here's an example:

Assign 20 soldiers to Joe Smith. Assign Joe Smith to General Ping
Shau. Have Ping Shau go to Riverton and have Joe Smith go to
Clarksville.

When Ping Shau arrives in Riverton, he will have Joe Smith and Joe's 20 soldiers depart for Clarksville,
while Ping Shau will remain in Riverton. In other words, the 20 soldiers that were placed under Joe's
command earlier remained under his command even though he was temporarily assigned to General Ping
Shau.

It is also possible to assign items, unnamed characters, and even named characters to a different player. For
example, you may want to loan or surrender a skilled individual, a combat brigade, or even an entire army to
another player for whatever reason. When this occurs, the assigned entities will be under the complete control
of the other player, and will remain under his control until he re-assigns them back to you (if ever). During
this time, you may not even QUERY them or order them to REPORT to you. (You can, of course, ask the
other player to provide you with this information.) Also, the other player will be responsible for paying them.
In other words, when you assign someone or something to another player, it is as if you never had control to
start with.

IMPORTANT!
It is strictly forbidden to assign items or people to another player that does not want them.
For example, you might be tempted to give several loads of unneeded stone to an
unknowing enemy in the hope that it will slow him down before he discovers the deed. If
this occurs, the gamemaster should be notified and the offending player will be evicted
from the game.
You may assign yourself (i.e., your lead character) to one of your own subordinates. This can be useful if you
don't want other players to know who your leader is. You may not , however, assign yourself to a different
player, either directly or indirectly (by first assigning yourself to a subordinate and then assigning the
subordinate to another player).

See also the JOIN command.

ATTACK [ Table of Contents ]

Use the ATTACK command to attack characters controlled by another player. Here is an example:

Assign 500 soldiers and 500 horses and Bishop Na'Equila to Tom
Ballard, and have him go to Kitesta and attack John May.

If John May is not present, then no attack will take place. If John May is present and if his player has control
of other personnel at the attack location that may be useful in the attack, then they will automatically come to
his aid. If so, you will not be aware of them until after the battle starts.

If you do not name anyone in an ATTACK order, then the attack will be against whoever currently secures
the location:

Go to Kitesta and attack.

If Kitesta is secured by Joe Flint, then the above order would be equivalent to "attack Joe Flint".

If you have other characters at the battle location, they will not take part in the attack. For example, if you
have other groups in Kitesta in addition to those of Tom Ballard, then they will stay clear of the fighting.
Also, you may only specify one attacker. If you want more than one group to attack, then first combine them
into a single group. Here is an example:

WRONG: Have Tom Ballard and Mike Bellows attack John May.

RIGHT: Assign John Bellows to Tom Ballard and have him
attack Mike May.

Also, if you give separate ATTACK orders to more than one attacker, then the attacks will occur in sequence.
Here is an example:

Have Tom Ballard attack Mike May. Have John Bellows attack Mike
May.

In the above example, John Bellows will not attack Mike May until the attack by Tom Ballard has concluded,
even if both attackers are ready to fight at the same time.

It is also possible for the characters of other players to aid someone in an attack. See the SUPPORT
command for details.

The purpose of an attack is to kill or capture as many of the enemy as possible.

Normally, the side that gives the ATTACK order will only attack if they appear to be at least as strong as the
defenders. If not, then no attack will occur. If the fight does start, then it will continue until either side takes
losses of more than 25% and decides to retreat. If both sides decide to retreat at about the same time, then
neither will actually retreat. Instead, the fight will stop so that both sides can lick their wounds. It will only
continue if another ATTACK order is issued. If one side does retreat and they were initially inside the walls
of the battle location, then they will retreat to outside the walls of the same location. Otherwise, they will flee
to an unnamed spot near the location, but not close enough to be seen from within the walls or just outside
the walls.

You may also specify the conditions of your attack by modifying the ATTACK command, as in the following
examples:

Cravenly attack John May.

Attack only if odds are 2 to 1 in your favor or better,
and retreat if any losses are taken.
Cautiously attack John May.

Attack only if odds are 1.5 to 1 in your favor or better,
and retreat if losses exceed 15%.
Bravely attack John May.

Attack even if odds are as bad as 1.5 to 1 against you,
and retreat only if losses exceed 35%.
Recklessly Attack John May.

Attack even if odds are as bad as 2 to 1 against you,
and retreat only if losses exceed 50%. In addition,
defender will not attempt to retreat until his losses
reach 35%.
Suicidally attack John May.

Attack even if odds are as bad as 5 to 1 against you,
and never retreat. In addition,
defender will not attempt to retreat until his losses
reach 50%.
Odds are based only on appearances, since you have no way of knowing what skills or magic items the
enemy possesses.

If you definitely want to attack, then use the adverb definitely. You may combine this with another adverb to
set the retreat conditions. Here are some examples:

Definitely attack John May.

Attack regardless of the odds, but retreat if losses exceed
25%.
Definitely bravely attack John May.

Attack regardless of the odds, but retreat if losses exceed
35%.
You may also specify more than one person to attack, as in the following example:

Recklessly attack John May and Harry Islington and Pierre Olivier.

This is especially useful if you are not sure which characters are controlled by other players.

You may not attack someone unless both parties are in compatible locations. To attack someone inside or just
outside a location, the attacker must be either inside or just outside the location. To attack someone near a
location (but not inside or just outside), the attacker must also be near the location (but not inside or just
outside).

When an attack attempt is near a location, the chance of even finding the target will depend mostly on how
many people are in the target group(s), and, to a lesser extent, on how many people are in the attacking
group(s).

If you are outside a location that has been secured by another player and you want to attack someone that is
inside, then the attack order must contain the name of at least one character that is controlled by the securing
player and that is inside the location. Otherwise, no attack will take place.

If you are inside a location that has been secured by another player and attack someone that is also inside,
then the characters of the player that have secured the location will automatically defend against the attack,
even if you did not explicitly name them in the attack order.

A person that has secured a location will have a 25% increase in their overall combat effectiveness if they are
attacked, in the initial stage of the battle only.

If an attacker attacks a much stronger opponent, then there is a chance that some of his subordinates (both
named and unnamed) may desert to the other side.

When the battle ends (for whatever reason), you will receive a summary of what happened as well as a report
on the current status of your characters. Thus, there is no need to issue a REPORT order immediately after an
ATTACK order.

In fact, it is generally a bad idea to issue any orders at all that are to immediately follow an attack, unless you
are absolutely certain that your side will win. And even if you win a battle, your forces may be in disarray,
some of your leaders may be dead or captured by the enemy, and so on. Because of this, any orders that are
immediately executed after an attack will often either fail or have unpredictable results.

There are several things, magical and non-magical, that can affect the outcome of a battle:

SKILLS - High combat skill levels will provide better leadership, high religion skill
levels will provide better morale, and each will have a multiplicative effect on the
overall effectiveness of the entire group. In addition, sailing skill is half as
effective as combat skill in actual melees. However, sailing skill does not provide any
multiplicative effect on the overall effectiveness of the group. Other skills have no
value whatsoever in combat.
ARMOR - All combatants are assumed to have basic armor and shields when in combat. The
special item armor , which can be purchased or constructed, is especially high quality
and can provide significant additional advantages during combat. A soldier with special
armor will fight like one-and-a-half ordinary soldiers. If the amount of armor carried
by a group exceeds the number of combatants in the group, then the excess armor will
have no effect.
WEAPONS - All combatants are assumed to have basic weapons when in combat. The special
item weapon , which can be purchased or constructed, is especially high quality and can
provide significant additional advantages during combat. A soldier with a special
weapon will fight like one-and-a-half ordinary soldiers. If the amount of weapons
carried by a group exceeds the number of combatants in the group, then the excess
weapons will have no effect.
BATTERING RAMS and SIEGE TOWERS - If a location is secured by another player and is
100% fortified, then any attack from outside will automatically fail unless the
attacker has battering rams or siege towers or both. Even a small amount of
fortification can deter an attacker that does not have these items. In general, the
more rams or towers that the attacker has, then the easier it will be to overcome the
fortifications (within reason, of course). Also, each ram will require about 25 people
and each tower will require about 50 people to be effectively used. Siege towers are
about twice as effective as battering rams.
CATAPULTS - Catapults are used to soften up the enemy before the main battle. They will
only be used if the attacker is initially outside the walls of a secured location and
attacks someone on the inside. If the attacker uses catapults, then the defenders will
return fire using catapults if they have any. A catapult requires 25 people to operate,
and excess catapults will not be used. Also, whenever catapults are used, everyone
inside the location that has combat skills and that is not controlled by the attacking
player will automatically aid the defenders. It's a very bad idea to attack a location
with catapults if your own people are on the inside.
HORSES - A soldier on a horse will fight like one-and-a-half foot soldiers. If the
number of horses in a group exceeds the number of combatants in the group, then the
excess horses will have no effect.
ELITE TROOP UNITS - An elite troop unit has the combat effectiveness of the same number
of ordinary soldiers times the square root of their level. Partial levels are ignored.
For example, if an elite unit with level 7 (square root = 2.65) has 100 soldiers, then
it will have the combat effectiveness of 265 ordinary soldiers.
SUMMONED MAGICAL CREATURES - Summoned creatures (skeletons, griffins, demons, dragons,
etc.) are not only powerful fighters and tough to kill, but they also instill fear into
their opponents. This will have a net multiplicative effect on the combat effectiveness
of the entire group that controls them. The more such creatures there are and the more
powerful they are, then the greater the effect will be.
Special armor, special weapons, and horses may be combined to achieve a cumulative effect. For example, 10
soldiers on 10 horses with 10 armor and 10 weapons will fight like 25 ordinary soldiers.

There will be times when you will want to attack someone and quickly move on to a new location. However,
if you take prisoners during the attack and the prisoners have large quantities of heavy materials, it could
slow you down considerably. Also, if you are departing by galley, it could even cause your ships to sink.

You can avoid this by having the attacker DISCARD all of his "garbage" immediately after the attack. Here
is an example:

Have Genghis Khan go to Tashendi and attack John The Dagger and
discard all his garbage and go to Madegi Doy.

When the computer processes a "discard garbage" command, it will discard all of the heavy items in the
possession of all of the prisoners in the group. Heavy items consist of catapults, galleys, battering rams, siege
towers, wagons, copper, iron, stone, and wood.

AWAIT [ Table of Contents ]

See the WAIT FOR command. WAIT FOR and AWAIT are synonymous and may be used interchangeably.

BLESS [ Table of Contents ]

A person with religion skill may attempt to bless himself or another person in order to reduce the chance that
something bad will happen. To bless a person, use the BLESS command, as in the following examples:

Bless Joe Flint.
Have Primate Julius III bless Mike Myers and John Cadbury.
Have Bishop Linda Gonzalez bless herself.
Have Friar Tuckitin and Sister Lois Park bless themselves.

Note that you may use the reflexive pronouns myself , yourself , himself , herself , or themselves if the
supplicant is to bless himself, herself, etc.

The person doing the blessing and the person being blessed do not have to be in the same location. You may
even attempt to bless characters of other players. If you do so, they will know they have been blessed, but
will not know who did it.

As with all requests for miracles, the chance of success will depend on the amount of religious power that the
supplicant has accumulated, and power may be taken by the god even if the blessing is not granted. If a
supplicant requests a blessing but has no available religious power, then the god may become angry and
punish the supplicant.

If the request is granted, the person blessed will be considerably less likely to suffer from random events.
Specifically, whenever there is a probability that something bad will happen to the person, that probability
will be cut in half. For example, if a blessed person is attacked in combat and the chance of a hit is 70%, then
the actual chance will be reduced to 35%.

Only named persons may be blessed. However, even unnamed characters can benefit if their leader is
blessed. For example, if the captain of an overloaded ship is blessed, then the chance that the ship will
capsize is reduced by half. If the leader of a party searching for treasure is blessed, then the chance of success
will be greater. In combat, a blessed person will both fight and lead better. When working, you'll make more
money. When building, construction will be at a faster pace. When recruiting, you will be able to find more
recruits. When mining or gathering, more material will be obtained in the same amount of time. When
buying, you will be more likely to find what you want at lower cost, and when selling things, you will be able
to sell more at a higher price.

A blessing will remain in effect a number of days equal to the religion skill level of the blesser. Blessings
may not accumulate.

A CURSE command may be used to cancel a BLESS command and vice-versa. See the CURSE command
for more details.

BORROW and REPAY [ Table of Contents ]

If you need extra gold, you may attempt to BORROW it. Here are some examples:

Assign Archbishop Harold Maginta and Wizard Kalipomaski and 250
soldiers to Joe Flint and have him go to Tashendi and borrow
1000 gold.
Have worker Iyam Nobody borrow 5.
Go to Umadosh and borrow and definitely buy every horse and go
to Tashendi.

Note that the word gold is optional.

Your chance of success will depend on the location (it's easier to find lenders in larger cities), how much gold
you need, how much you are already in debt, and on how impressive the person requesting the loan is. In the
above examples, worker Iyam Nobody will have a very hard time getting a loan, while Joe Flint will have a
much greater chance of success.

If you want to borrow as much as you can get, then do not specify the amount to borrow, as in the last
example above.

The interest rate is 1 percent of the current balance per game week.

You are not required to make any payments for approximately 4-5 weeks.

Each week thereafter, you will be required to pay at least 10 percent of the current balance. Your status report
will indicate how much is due at any time. Each payment must be at least 10 percent of the current balance or
it will be ignored. If you make payments in advance, they will add to the grace period before the next
payment is due.

Use the REPAY command to make payments:

Have Joe Flint repay 45 gold.
Go to Madegi Doy and take all the gold from Harry Johnson and
repay.

The word gold is optional. If you do not specify the amount to repay, then the computer will assume that you
will try to pay off the entire balance, if possible. If you do not have sufficient gold to do so, then whatever
gold you do have will be used.

Repayment may be made anywhere and by any of your characters. Payments do not have to be made by the
person who made the loan or in the location where the loan was made.

If the required minimum payment is not made, there is a chance that the bankers guild will hire assassins to
kill your LEADER. (Yes, they will know who you are, even if some other character actually took out the
loan.) The assassination attempts may succeed or fail, depending on how powerful you are (which will
depend on the sum of all of your skill levels) and on how determined they are (which will depend on how far
behind you are in your payments).

Keep in mind that if your lead character is killed, you are out of the game, although you are certainly
welcome to start over again using different character names.

BUILD, CONSTRUCT, and MAKE [ Table of Contents ]

If you want to build constructible items from raw materials, use the BUILD/CONSTRUCT/MAKE
command. BUILD, CONSTRUCT, and MAKE are synonymous and may be used interchangeably. Here are
some examples:

Assign 20 soldiers and 24 wood to Engineer Bill Denton,
and have him build 6 catapults.
Go to Nandigwa and gather 500 wood. Then go to Tashendi and
build 1 galley.
Have Joe Madison buy 2 iron and build 10 armor.

Any constructible items may be built as long as the person given the order has an engineering skill level of at
least 1. However, a person with such a low skill level will take a very long time to build the items. The higher
the skill level, then the more quickly the job will be done.

The construction time also depends on the number of people in the lead engineer's group. In general, more
workers can accomplish the job more quickly.

Each item being built requires that the lead engineer have direct possession of a quantity of the required raw
material equal to one-fifth of the basic cost of the item (the only exception to this is when building
fortifications - see the FORTIFY command). Weapons and armor require iron. All other items require wood.
For example, a catapult (basic cost = 20) requires 4 wood, a galley (basic cost = 1000) requires 200 wood,
and a suit of quality armor (cost = 5) or a quality weapon (cost = 5) requires 1 unit of iron. Raw materials
will be consumed as they are used, and there must always be enough available to construct at least one item.
Thus, even if you do not have enough materials at the beginning of construction to build all of the items, you
can provide more as it is needed. If the workers run out at any time, then construction will stop.

During construction, you may add workers or raw materials to the group by means of the ASSIGN/GIVE
command. You may also remove raw materials or workers from the group by means of the
GET/OBTAIN/TAKE command, although this may slow down or stop construction.

Instead of a quantity, you may specify a time limit using the preposition for , as in the following example:

Build armor for 6 days. # Or until I run out of iron.

See the WAIT FOR command for a more thorough discussion of how to use the preposition for and the
optional adverb exactly. If you do not use exactly , then the current item being constructed will be completed
before stopping.

BUY and PURCHASE [ Table of Contents ]

Use the BUY command if you want yourself or one of your subordinates to purchase something. BUY and
PURCHASE are synonyms and may be used interchangeably. Here are some examples:

Buy 20 horses. # I will buy 20 horses.
Have Jim Thomas purchase 2 catapults.
Give Captain Lois Park 7000 gold.
Have her go to Albatross City and buy 1 galley
and 40 slaves and recruit 20 sailors.
Have Joe Flint go to Irontown and buy 20 copper and 10 iron,
and go to Umadosh and sell them.

See Appendix B for a complete list of the items that may be purchased in the game and their costs.

An attempt to purchase something may not always succeed. In some locations, what you seek may simply not
be available. For example, if you attempt to buy a galley in a small desert outpost, you will definitely fail.
And some items, such as catapults, will be hard to find almost anywhere.

It is also possible that the quantity available may be less than what you want. In general, the availability of an
item will depend on the location. Almost anything can be found in any quantity in large towns and cities,
while you may be out of luck in places that have fewer people.

The only exception to this is that the raw metals silver, iron, and copper can usually be found in larger
quantities in hilly or mountainous areas where mines are plentiful. (It makes no sense to buy gold, since gold
is the standard and is always traded at exactly one for one.) Also, wood is more readily available (and
cheaper) in forested areas.

If the person doing the buying has skill in trading, then he may be able to buy the items at a discount. In
general, the higher his skill is in trading then the greater the discount he can receive.

The costs shown above are maximum costs. The actual amount you pay may be less depending on the item
and the location. For example, if you purchase silver metal in a mining region that is rich in silver, you will
pay less than 1 gold for each unit of silver.

If you want to keep trying until you obtain the exact quantity specified, then place the adverb definitely
immediately before the verb BUY. Here is an example:

Definitely buy 100 horses and 10 armor.

In the above example, if you find fewer than 100 horses, then you will try again until you succeed. You will
then try to buy 10 armor, and will keep trying until you succeed. Keep in mind that you can always cancel the
order by using one of the HALT/STOP commands.

Instead of a quantity, you may specify a time limit using the preposition for , as in the following example:

Buy horses for 6 days. # Or until I run out of money.

See the WAIT FOR command for a more thorough discussion of how to use the preposition for and the
optional adverb exactly. If you do not use exactly , then the current purchase will be completed before
stopping.

BUY PASSAGE [ Table of Contents ]

Use the BUY PASSAGE command if you want yourself or one of your subordinates to travel by sea, but you
do not possess a galley. Here are some examples:

Buy passage to Kitesta.
Have Jim Thomas buy passage to Amesbok and Im Prok.

Travel to Im Prok via Amesbok.
Unlike the SAIL command, the BUY PASSAGE command must specify a destination that has a single, direct
sealane connecting it to the starting location. If there is more than one stop along the way, then they must be
specified separately, as in the second example above.

An attempt to buy passage may not always succeed. This is most likely to occur if the group is too large. You
can try to improve your chances by splitting up the group into smaller groups, but if you do so, the groups
will not travel together.

If you fail to find passage but want to keep trying, then use the adverb "definitely", as in the following
example:

Have Joe Flint definitely buy passage to Kitesta.
The cost for passage is equal to the total encumbrance of the group in gold. For example, passage for a group
leader, 10 soldiers, and 11 horses will cost 33 gold. See Appendix B for a complete list of items and their
encumbrances.

CAPTURE [ Table of Contents ]

Use the CAPTURE command if you want to make prisoners of one or more specific people. Here are some
examples:

Go to Kitesta and capture Jamu Penda and Billy The Kid.
Have Joe Flint cautiously capture Mary Tarrington.

The CAPTURE command is identical to the ATTACK command, except that you are also ordering your
troops to make a special effort not to kill the named individuals, but to try to capture them instead. This will
increase the chance of a successful capture but will also make their job more dangerous. As with ATTACK,
you may also take other prisoners as well.

Capturing a person is most useful if the character is another player's leader or a person that is very important
to another player. Once captured, a person can be either ransomed, killed, freed, or enslaved.

It makes no sense at all to capture, kill, or enslave non-player characters, since they will never be ransomed
and their families and friends will remember for a long time.

Prisoners may try to escape. The chance of success will depend on the overall skill level of the prisoner and
on the number of people guarding him.

CHARGE and RECHARGE [ Table of Contents ]

Use the CHARGE/RECHARGE command to have a magic-user transfer power from himself to a magical
crystal, orb, or wand. CHARGE and RECHARGE are synonymous and may be used interchangeably. Here
are some examples:

Recharge Madingo.
Have Merlinus recharge Hasimpa by 10 points.
Charge Ampu to 75 power and Wasute by 7 power and
give Ampu to Merlinus.
Have Ameriki charge Nenikasta to 30 points and give it
to me.

Note that the word points or power is optional.

Use the preposition by to specify the amount of power to add to the item. Use the preposition to to specify the
desired final level. If neither quantity is specified, then the character will transfer as much power as possible
to the item.

A character may charge a magical item that is not in his possession as long as the character that does possess
it is in the same location and is controlled by the same player. Here is an example:

Take Gilopeshta from Merlinus and have him and Joe Bunnions
and Gandamiko immediately charge it.

Only magic power may be transferred to a magical item. Religious power may not be transferred.

COLLECT and GATHER [ Table of Contents ]

If you wish your characters to cut down trees for wood or to quarry stone in a location, use the
COLLECT/GATHER command. COLLECT and GATHER are synonymous and may be used
interchangeably. Here are some examples:

Go to Irontown and gather stone.

Me and my group will quarry stone in Irontown for 1 week.
Assign 250 soldiers to Bill Fenton and have him collect wood
for 5 days.
Have Baldur repeatedly gather stone for 10 hours and give it
to Engineer Tom Baldwin.
Have George Doone go to Nandigwa and collect wood for 5 days
and give it to me.

If you do not specify the amount of time to COLLECT/GATHER, then it will be assumed to be exactly one
game week = 7 game days.

See the WAIT FOR command for a more thorough discussion of how to use the preposition for.

Note that the pronoun it can be used to refer to whatever was successfully collected.

Instead of specifying the collection time, you can specify the amount to collect. Here is an example: Have
Engineer Tom Baldwin gather 40 wood and build 2 siege towers. In the above order, the engineer will spend
as much time as necessary to gather 40 units of wood before building the tower. Note that the computer
calculates the amount gathered 1 full day at a time. Thus, you may end up with more that the requested
amount.

When you give a COLLECT/GATHER command to a group leader, the group leader provides the
supervision, and everyone else in the group will provide the labor. The quantity of stone or wood collected
will depend on the location and the number of laborers. No special skill is needed to collect stone or wood.

You may only collect stone in hilly or mountainous areas. You may only collect wood in forested areas. If
you do so in other locations, you will just waste your time.

Stone and wood are like any other items, and can be bought and sold. They can also be used to build things
(see the BUILD and FORTIFY commands).

COMBATANT [ Table of Contents ]

See the NONCOM command.

COME [ Table of Contents ]

See the GO command.

CONJURE [ Table of Contents ]

Use the CONJURE command to attempt to conjure a magical item for temporary use. Here are some
examples:

Conjure an amulet of trading.
Have Merlinus conjure a wand of conjuring.
Conjure a ring.
Have Delphinus conjure an orb.
Conjure a wand of teleport.

Note that when conjuring an amulet, you must also specify the skill desired. Similarly, when conjuring a
wand, you must specify the magical spell that the wand will provide. You may use any of the following
words to describe a wand: conjure, conjuring, conjuration, fly, flying, probe, probing, summon, summoning,
teleport, teleporting, teleportation.

When a CONJURE spell is cast, all of the magic user's magical power will be used (including any power in
crystals in his possession). The chance of success, as a percentage, will equal the power expended. For
example, if the spell-caster has a current power level of 62, then all 62 points will be expended and the
chance of success will be 62 percent.

A spell-caster must have a magic skill level of at least 25 to cast a CONJURE spell.

There is no way to specify the power or skill level of the item obtained.

If the conjuration is successful, the item will return to whence it came after a number of days approximately
equal to the power expended to obtain it. For example, if 62 power was expended, then the item will remain
with the spell-caster (or whoever he gives it to) for a total of approximately 62 days.

You will be notified when a magical item disappears.

CREATE [ Table of Contents ]

Use the CREATE command to create an elite troop unit. Here are some examples:

Create Gordy's Killers using 250 soldiers.
Have General Wazawaza create The Wazoo Troop with 1200
soldiers.

An elite troop unit consists of any number of soldiers. The unit is identified by name; e.g. "Green Berets".
Each unit has a combat level associated with it, just as if it were a named character, and each soldier in the
unit fights at this level.

Elite units are always in training, and their level will continue to rise because of this training. However, there
is no additional cost for this training and a teacher is not needed. Because of this, the combat level will not
rise as rapidly as if they were learning under a teacher, but will average about 1 partial point per week. Their
level (but not their partial level) will be shown on the status report of the player that controls them, but not on
the reports of other players. (See the STUDY command for an explanation of partial skill levels.)

The combat level of the group leader of the unit will not automatically rise along with the unit's. However,
the leader may be given separate STUDY or TEACH orders (or any legitimate order, for that matter) while
the unit is training. In fact, the unit will continue to train even while traveling.

Since elite units are constantly training, they may not be used to TAX or SECURE a location, nor will they
take part in BUILD, FORTIFY/UNFORTIFY, MINE, SEARCH, WORK, or GATHER operations. Also, they
are not counted as soldiers in IF statements, and can not act as rowers on a galley.

Elite troops fight at the level of their unit, but do not provide leadership, and must always be part of a larger
group; i.e., they cannot be independent like named characters, but instead must always have a group leader,
and orders should be given to the group leader, not directly to the elite unit.

The salary for an elite troop unit will be the number of soldiers times the combat level. For example, if the
level is 7, and the unit has 100 soldiers, then the monthly salary will be 700 gold.

The name of an elite unit is specified in exactly the same way as for a named character and has the same
limitations (32 characters maximum, and no reserved words, periods, commas, or double quotes may appear
in the name).

Use the pronoun "it" when referring to elite units. Never use "them":

WRONG: Create The Redhawks using 200 soldiers and assign them
to Joe Flint.
RIGHT: Create The Redhawks using 200 soldiers and assign it
to Joe Flint.

Elite units may only be created using soldiers, and will start with combat level 1. They may not be created
from sailors or workers.

An elite unit will not be created if the agent has fewer soldiers than the number specified. For example, if a
character tries to create a unit with 100 soldiers but has only 99 soldiers, then the order will fail.

Soldiers in a unit may die during combat, but new soldiers can not be added to an existing unit.

CURE [ Table of Contents ]

See the HEAL command. HEAL and CURE are synonymous and may be used interchangeably.

CURSE [ Table of Contents ]

A person with religion skill may attempt to curse another person in order to increase the chance that
something bad will happen. To curse a person, use the CURSE command.

The CURSE command is in all respects the exact opposite of the BLESS command, and the two commands
may even be used to cancel each other. Specifically, if a CURSE is successful on a person that is already
blessed, then the duration of the blessing will be reduced by the duration of the curse, and the excess
duration, if any, is the amount of time that the curse will last. The exact opposite occurs if a BLESS
command is used on a cursed person.

You will know if you have been cursed, but you will not know who did it.

See the BLESS command for more details.

DISCARD, DISMISS, FREE, and RELEASE [ Table of Contents ]

Use the DISCARD, DISMISS, FREE, or RELEASE command if you want to free prisoners, get rid of named
characters, unnamed characters, elite troop units, or items. DISCARD, DISMISS, FREE, and RELEASE are
synonymous and may be used interchangeably. Here are some examples:

Dismiss Wizard Yemishoka. # He costs me too much.
Discard 2 stone and 6 horses and 10 sailors.

Have Joe Flint free 5 slaves.
Have Mike Fenton dismiss The Green Berets.

When people are dismissed, they leave your control. Freed prisoners are returned to the control of the
original player, named characters become independent characters under the control of the computer, slaves
are freed, unnamed characters and elite troops simply blend into the population, and items effectively
disappear. If a named character has items in his possession or is the leader of a group, then the items and
everyone in his group remain with him and are no longer under your control.

Keep in mind that it might be better to SELL items rather than discard them. These commands simply throw
the items away, while you will actually get some gold if you SELL them.

There will be times when you will want to ATTACK or CAPTURE someone and quickly move on to a new
location. However, if you take prisoners during the attack and the prisoners have large quantities of heavy
materials, it could slow you down considerably. Also, if you are departing by galley, it could even cause your
ships to sink.

You can avoid this by having the attacker DISCARD all of his "garbage" immediately after the attack. Here
is an example:

Have Genghis Khan go to Tashendi and attack John The Dagger and
discard all his garbage and go to Madegi Doy.

When the computer processes a "discard garbage" command, it will discard all of the heavy items in the
possession of all of the prisoners in the group. Heavy items consist of catapults, galleys, battering rams, siege
towers, wagons, copper, iron, stone, and wood.

ENEMY [ Table of Contents ]

See the ALLY, ENEMY, and NEUTRAL command description.

ENSLAVE [ Table of Contents ]

If you want to convert a prisoner to a slave, use the ENSLAVE command. Here are some examples:

Enslave Mark Hobart and Nancy Eaton, and sell 2 slaves.
Have Joe Flint enslave Dennis Morrow and give 1 slave to
Queen Rachel.

IMPORTANT! Note in the above examples that you cannot use the pronouns he , them , or it to refer to the
slaves, since their nature has completely changed. You must specify the actual number of slaves.

If the prisoner has valuables in his possession, make sure that you have someone TAKE them from him
before enslaving him. Otherwise, the valuables will be lost.

Only a prisoner under your control may be enslaved. Once a person has been enslaved, he may never again
be referred to by name.

EXECUTE [ Table of Contents ]

See the KILL command. KILL and EXECUTE are synonymous and may be used interchangeably.

EXPLORE [ Table of Contents ]

See the SEARCH command. EXPLORE and SEARCH are synonymous and may be used interchangeably.

FLY [ Table of Contents ]

Use the FLY command to magically fly from one location to another. Here are some examples:

Fly to Kitesta and Madegi Doy.

Fly to Kitesta via Madegi Doy.
Assign Joe Flint and Bishop Coranona to Merlinus, and
have him fly to Tashendi, and have them study
engineering for 4 weeks.

The spell-caster must be the leader of whatever group is flying.

The magical power needed to fly is one-fifth (1/5) of the total encumbrance of the group (rounded up to a
whole number).

Unlike the GO/COME/MOVE/TRAVEL and SAIL commands, with FLY it is possible to enter a secured
location, even if the person securing the location would otherwise deny you entry. If you want to remain
outside of the gates/walls, then use the word outside , as in the following example:

Fly to outside Madegi Doy.

If you want to remain near the location, but far enough away that you cannot be seen from within or just
outside, then use the word near , as in the following example:

Fly to near Madegi Doy.

Magical flight in miles per hour is equal to the spell-casters skill level in magic. For example, a mage with a
magic skill level of 75 will travel at 75 miles per hour (1 mile = 1.61 kilometers). Flight is always in a
straight line between initial location and destination (i.e. 'crow-flight' distance), and may be done over any
terrain, including bodies of water. Approximate distances can be determined by looking at the map provided
by the Gamemaster.

FORTIFY and UNFORTIFY [ Table of Contents ]

If you want to build stone fortifications around a location, use the FORTIFY command. If you wish to
remove existing fortifications, use the UNFORTIFY command. Here are some examples:

Have Joe Flint go to Plugby and gather stone for 7 days and go
to Madegi Doy and fortify it.
Buy 1000 stone and fortify Kitesta.
Go to Irontown and buy 1000 stone and fortify.
Have Engineer Mack Donalds unfortify Tashendi.

Note that the name of the location or the pronoun it is optional but may be included for readability. The
computer will always assume that the location of the character when the command is executed is the location
to fortify or unfortify.

You may not FORTIFY/UNFORTIFY uninhabited locations.

The person given the order must have an engineering skill level of at least 1. (However, a person with such a
low skill level will take a very long time to build or remove any fortifications!) The greater the skill level
then the faster the job will be completed.

Construction/removal time will also depend on the number of people in the engineers group. These people do
not require any special skills. Removing fortifications will be twice as fast as building them.

Construction will proceed until the group runs out of stone or the group is given a HALT or STOP command.

The stone obtained when removing existing fortifications may not be reused.

While it is possible to fortify a location beyond 100%, the additional fortifications will have no effect.

You may also specify an approximate time limit using the preposition for , as in the following example:

Fortify Kitesta for 6 days. # Or until I run out of stone.
Unfortify Kitesta for exactly 2 weeks.

See the WAIT FOR command for a more thorough discussion of how to use the preposition for.

See the ATTACK, CAPTURE and SECURE commands for information on the use of fortifications.

FREE [ Table of Contents ]

See the DISCARD command. DISCARD, DISMISS, FREE, and RELEASE are synonymous and may be
used interchangeably.

GET, OBTAIN, and TAKE [ Table of Contents ]

Use the GET, TAKE, or OBTAIN command if you want one character to obtain characters or items from
another character under your control (a prisoner is considered to be under your control). GET, TAKE, and
OBTAIN are synonymous and may be used interchangeably. Here are some examples:

Take 20 gold from Billy Bob.
Have Mike Jones go to Kitesta and obtain 3 workers and 20 soldiers
and 23 horses from Joe Flint, and Father Michema and 1 horse
from Bishop Doniman.
Take 90% of the gems from Hanna Lando.

The GET/TAKE/OBTAIN command performs exactly the same function as the ASSIGN/GIVE command
except that the recipient is the agent of the transfer rather than the donor. Thus, the event will take place when
the recipient is ready rather than when the donor is ready. In fact, the donor can be doing something else
while the recipient is carrying out this command. Here's another example:

Have Mike Felton study magic for 6 weeks.
Have John May go to Tashendi and obtain 10 horses from him.

In the above example, Mike Felton will give 10 horses to John May as soon as John May arrives, even if
Mike is still busy studying.

One other difference between GET/TAKE/OBTAIN and ASSIGN/GIVE is that you can give someone or
something to a character controlled by another player, but you can not take someone or something from such
a character.

If GET/TAKE/OBTAIN is not followed by the preposition from , then the computer will assume that you want
one or more named characters to join you. Here is an example:

Sail to Tashendi and get Joe Fenton and Tom Sawyer,
and then sail to Madegi Doy.

The above is exactly the same as:

Sail to Tashendi and assign Joe Fenton and Tom Sawyer to me,
and then sail to Madegi Doy.

GIVE [ Table of Contents ]

See the ASSIGN command. GIVE and ASSIGN are synonymous and may be used interchangeably.

GO, COME, MOVE, and TRAVEL [ Table of Contents ]

Use the GO/COME/MOVE/TRAVEL command to have someone travel to a new location on foot or on
horseback. (To travel by boat or by air, use the SAIL or FLY command.) GO, COME, MOVE, and TRAVEL
are synonymous and may be used interchangeably. Here are some examples:

Go to Peshandi. # I will go to Peshandi.

Give 1 horse to Adept Kalisto.
Have him travel to Willis Grove and Riverton.

Kalisto will ride to Riverton via Willis Grove.
Have Mike Fenton recruit 100 soldiers and come to Madegi Doy and
assign 80 soldiers to me.

The amount of time it takes to travel between locations depends on the distance and on the quality of the
roads. Distances and road quality can be determined by looking at the map provided by the Gamemaster.

IMPORTANT!
Spoils of Empire is not a game of exploration. For this reason, travel is limited to pre-
defined routes that are shown on the game map.
When going to a location, it is possible that another player may be in control of the location (see the
SECURE command). If so, your party may be denied access. If this occurs then the travelers will remain
outside the gate/walls.

There may also be times when you intentionally wish to remain outside the gate/walls. If so, use the word
outside between to and the name of the location. Here is an example:

Have Joe Flint move to outside Madegi Doy.

If you want to remain near the location, but far enough away that you cannot be seen from within or just
outside, then use the word near , as in the following example:

Go to near Madegi Doy.

When there is more than one named location between the starting point and the destination, the computer will
determine the fastest route to go by, even if it is not necessarily the shortest in length. However, the computer
will not be able to determine the correct route if there are more than 10 locations between the start and end
points. If you wish to travel farther than this, then provide intermediate points, as in the following example:

Go to Je Bin Noi and Imayasa.

Go from Londanum to Imayasa via Je Bin Noi.
The computer will reject any GO/COME/MOVE/TRAVEL order if there are no land routes linking the initial
and final locations, such as if the locations are on different islands or continents. If you wish to travel by both
land and sea, then issue separate GO and SAIL orders.

If the traveling group has horses, then travel time will be reduced depending on the number of horses
provided. If at least one horse is provided for each person in the group, then they will travel at the maximum
speed possible. If the group is also carrying heavy items (such as stone or metals), then they will move at a
slower rate, unless they have sufficient extra horses to pull the heavier items. As a general rule, if the total
encumbrance of the group is equal to the number of horses, then the speed will be doubled, and
proportionately less if the number of horses is less than the total encumbrance. Excess horses have no effect.
See Appendix B for the encumbrances of people and items. If the group has possession of a galley, then they
will not be able to move at all. (To travel on the galley, use the SAIL command).

If the traveling group possesses both wagons and horses to pull them, then heavy loads will move much
faster. Specifically, encumbrance will be reduced by 25 for each wagon IF there is also at least one horse to

pull it. Encumbrance can never become negative. Each excess wagon will actually add 10 to the
encumbrance. For example, if a group has an encumbrance of 210, but also has 7 horses and 7 wagons, then
the net encumbrance will be 210 - (7 x 25) = 35. However, if it has 8 wagons, then the net encumbrance will
be 45.

HALT and STOP [ Table of Contents ]

Use the HALT or STOP command to have characters stop their current activity and all pending activities that
were queued but not yet started.

By default, the character ordered to HALT or STOP will first complete the order that is currently in progress
(if any), but all additional orders waiting on the queue will be canceled. To have a character stop
immediately, place the adverb "immediately" directly before the verb.

Use the HALT command for an unplanned stop. Use the STOP command for a planned stop.

The planned STOP is queued just like all other commands and will be executed in sequence. Here is an
example (assume that Joe Flint is currently in the mining town of Plugby):

Have Joe Flint mine silver for 3 weeks.
Go to Plugby and immediately stop Joe Flint and assign him to me.

In the above example, Joe Flint will start mining silver at his current location and will stop mining and join
your group as soon as you arrive in Plugby, even if he has not mined the full 3 weeks. In other words, the
whole thing was planned in advance (perhaps because you're not sure how long it will take you to get to
Plugby, and you want to keep Flint busy while you're on your way).

The unplanned HALT is queued for immediate execution. It will not be queued in sequence like other orders.
Here is an example:

My troops were just attacked in Kitesta. Have Joe Flint,
Mike Fenton, and the wizard Jadumipa drop everything they're
doing and go to Kitesta immediately.
Have Joe Flint and Mike Fenton and Jadumipa immediately halt
and go to Kitesta and report.

Planned STOP can be placed anywhere in your orders, since its timing will depend on the completion of
other orders. Unplanned HALT, however, should be placed at the very beginning of your orders, since it will
be executed immediately and will not depend on the completion of any other orders.

When you use the HALT or STOP command along with the adverb "immediately", any activities that were in
progress are halted along with any orders that were queued but not yet started. If you do not use
"immediately", then the order that is currently executing will continue until it finishes normally, but all
additional orders waiting on the queue will be canceled.

The effect that the use of "immediately" will have on orders in progress will depend on which order is being
interrupted, as follows:

For the BUILD/CONSTRUCT/MAKE command, the number of items built will be proportional to the
amount of time already spent on construction. Partially built items and the raw materials needed for them will
be lost. (Unfortunately, it's not practical for the computer to keep track of partially constructed items.)

For the FORTIFY/UNFORTIFY command, the amount of construction or removal done will be based on the
amount of time that the workers actually worked.

For the GO/COME/MOVE/TRAVEL, SAIL, and FLY commands, the location after the HALT or STOP
command will be the next stop on the current route if you use "immediately". If you do not use
"immediately", the trip will be completed before stopping. For example, if a character is traveling from
Irontown to Madegi Doy via Plugby and is between Irontown and Plugby when he receives an "immediately

HALT/STOP" order, then he will continue on until he reaches Plugby and will effectively stop there. If
"immediately" is not used, then he will complete the trip and stop in Irontown.

For the STUDY command, the amount learned will be based on the number of complete weeks spent
studying.

For the COLLECT/GATHER, MINE, TAX, or WORK commands, the amount gained will be based on the
total amount of time spent in the activity.

For all other commands, no progress at all will be made. For example, if a character had orders to recruit or
train soldiers but was stopped before he could finish, then no soldiers will be recruited or trained.

You may also specify a delay with a HALT/STOP order to indicate that the character should HALT/STOP a
specific time after the order is issued:

Have Joe Flint halt in 4 hours and go to Kitesta and join me.
Have Mike Bellows go to Pomye and stop Suleimana in 3 days and have
her go to Ivriot and join Genghis Khan.
Have Mike Bellows fly to Amesbok and report.

In the first example above, Joe Flint will continue what he was doing for 4 more hours before departing for
Kitesta.

In the second example above, when Mike Bellows arrives in Pomye, he will order Suleimana to continue
what she is doing for 3 more days and then go to Ivriot. Mike, however, will not delay at all - as soon as he
gives Suleimana the order, he will fly to Amesbok.

You may specify the time period in minutes, hours, days, weeks, or months. However, you may not mix time
units. If you need to specify a non-integral time unit, then express it in terms of a smaller unit. For example,
you can express 1 day and 3 hours as 27 hours.

You may also use the adverb exactly after the preposition in. It will have the same meaning as using
immediately before STOP or HALT:

Have Bill Gardner immediately halt in 2 weeks.
Have Bill Gardner halt in exactly 2 weeks.

Both of the above will accomplish the same thing.

HEAL and CURE [ Table of Contents ]

If you want a character to heal a wounded person (including himself), use the HEAL/CURE command.
HEAL and CURE are synonymous and may be used interchangeably.

Only characters with skill in religion have the power to cast magical healing spells.

Anyone with a religion skill level greater than zero has access to a quantity of religious equal to the skill
level. For example, a person with a religion skill level of 37 may control up to 37 points of religious power.
This power is expended whenever a HEAL/CURE spell is cast.

Expended religious power is regained at the rate of 1 point of per game day.

A completely healthy person has a health level of 100. If wounded in battle, this level will drop. If it ever
reaches zero, the person is dead.

If you want a healer to raise the health of himself or another character, use the HEAL/CURE command.
HEAL and CURE are synonymous and may be used interchangeably. Here are some examples:

Heal Joe Flint and Linda Chase.
Have McCoy cure me to level 90 and Joe Flint to 50.
Cure Mike Dawson by 20 points and me by 7.

Heal yourself to level 100 and have McCoy heal himself
by 22 points.

Note that the words level and point(s) are optional.

A healer and the person being healed must be in the same location.

If you want the healer to heal himself, then use one of the reflexive pronouns myself , yourself , himself ,
herself , or themselves.

If the amount of healing is not specified, then the healer will use as much religious power as he has to bring
the patient up to full health, if possible.

A healer needs 1 point of religious power for each five points of health restored, rounded up to a whole
number. For example, to restore 31 points of health requires 7 points of religious power.

Healing magic is useless in combat because magic requires both time and uninterrupted concentration, which
is impossible to achieve during the noise and confusion of a battle. For this reason, healers are essentially
useless in battle unless they also have skill in combat.

If you attempt to HEAL a dead person, the order will be automatically converted to a PRAY order.

HIRE [ Table of Contents ]

See the RECRUIT command. HIRE and RECRUIT are synonymous and may be used interchangeably.

INTERROGATE [ Table of Contents ]

If you want to interrogate a prisoner in order to learn who his leader or associates are, then use the
INTERROGATE command:

Interrogate Genghis Khan.
Have Mike Dawson interrogate Phil Anderson and Wizard
Wanakojama.
Interrogate Sweet Prudence for 6 days and report.

The chance of learning any useful information will depend on the total skill level of the interrogator (the
higher the better) and of the victim (the lower the better). However, higher level victims are more likely to
have valuable information. They are also less likely to die from the torture.

Note from the third example above that you can specify a time limit. See the WAIT FOR command for a
more thorough discussion of how to use the preposition for.

INVEST [ Table of Contents ]

If you wish to invest in the growth of a town, use the INVEST command. Here are some examples:

Invest 400 gold in Ostrina'o.
Have Bill Harrington invest all of his gold in Yodrina.

Investing gold in a town is the only way to increase its population. The money invested will be used by the
locals to improve infrastructure. This, in turn, will attract new people and new business.

You may not invest in uninhabited locations!

Once per game week, the computer will check how much gold has been invested in a community and
subtract an amount approximately equal to the current population divided by 100, and will increase the
population by approximately the same amount. For example, if a town has a population of 5500, and
someone has invested 150 gold, then 55 gold will be subtracted (leaving a balance of 95 gold for the

following week), and the population will increase by 55. All of the above numbers are approximate since
there is some degree of randomness in the process. Locations with fewer than 100 people can also be
increased, but will (on average) require more than one week to do so.

Any characters may invest in a town, and the investor does not have to actually be in that town when the
investment is made. Investments from more than one player are accumulated. The computer does not keep
track of who invested what.

Status reports for a location will show how much has been invested but not yet spent. Here is an example:

Other notable people in Jamestown (pop. 7703, forest, inv 230,
0.00% fortified, secured [308s] by Captain Mike Bellows):

In the above example, 230 gold has been invested in Jamestown, but has not yet been spent. During the next
weekly check, approximately 77 gold will be spent and the population will rise by about the same amount.

Players who SECURE a location should keep in mind that the number of soldiers needed to maintain security
will increase as the population rises, and that more fortifications will be required to completely FORTIFY the
location.

JOIN [ Table of Contents ]

If you want a character (and anyone in his group) to become part of a different group, then use the JOIN
command. Here are some examples:

Have Joe Flint go to Tashendi and join General Bill Hayden.
Go to Madegi Doy and join Captain Mike Holmes.

I will become part of Mike's group. I don't want other players to
think that I'm the real leader.
The JOIN command accomplishes exactly the same thing as the ASSIGN command, but allows you to give
the order to the character that is being assigned rather than to the one that is doing the assigning. In this way,
a character will be able to perform other tasks first.

See the ASSIGN command for additional information.

KILL and EXECUTE [ Table of Contents ]

If you want to kill a prisoner use the KILL/EXECUTE command. Here are some examples:

Execute Mack the Knife.
Have Joe Flint kill Billy the Kid.

You may only kill a named person who is your prisoner.

LURK and UNLURK [ Table of Contents ]

If you want someone to avoid detection, use the LURK command. Anyone who is lurking will conduct his
affairs quietly and discretely, and will try to blend into the crowd. The chance of success will depend on the
population of the location and the kind of security measures that other players may be taking at that location.
It will also depend on the size of the group that is trying to act inconspicuously.

In general, the chance of detection of a lurking individual or group will be reduced by a factor of 4. For
example, if the normal chance of being noticed is 40%, then the actual chance will be reduced to 10%.

The LURK command should only be used on the leader of a group. Everyone in the group will automatically
be included, as well as any others assigned later to the group. However, if one or more members of a lurking

group break off to start their own group, then they will not continue to lurk unless their new leader is
explicitly given a LURK order.

Use the UNLURK command to cancel LURK.

Here is an example:

Have Major Johnson lurk,
and go to Emerald City,
and recruit 100 soldiers,
and go to Riverton,
and unlurk.

Lurking will have no effect while traveling. Thus, in the above example, Major Johnson will only be
considered lurking while he is recruiting the soldiers. In fact, the above command could also have been
written as:

Have Major Johnson go to Emerald City,
and lurk,
and recruit 100 soldiers,
and unlurk,
and go to Riverton.

with exactly the same results.

When an individual or group successfully lurks, they will not appear at all in the status reports of other
players. In other words, they have successfully blended into the crowd and have not been noticed. However,
if lurking is not successful, they WILL appear in status reports, and the reports will mention that they were
acting suspiciously.

MINE [ Table of Contents ]

If you wish your characters to MINE a location, use the MINE command. Here are some examples:

Go to Irontown and mine iron.

Me and my group will mine iron in Irontown for 1 week.
Have Baldur mine gold for 10 days and silver for 3 weeks.
Assign 250 soldiers to Expert Miner George Doone and
have him go to Tola Village and mine silver for 8 days.

If you do not specify the amount of time to mine, then it will be assumed to be exactly one game week = 7
game days.

See the WAIT FOR command for a more thorough discussion of how to use the preposition for.

Instead of specifying the collection time, you can specify the quantity to mine. Here is an example: Have
Miner Tom Baldwin mine 40 gold. In the above order, the miner and his helpers will spend as much time as
necessary to gather 40 units of gold before stopping. Note that the computer calculates the amount gathered 1
full day at a time. Thus, you may end up with more that the requested amount.

When you give a MINE command to a group leader, the group leader provides the supervision, and everyone
else in the group will provide the labor. The quantity of metal mined will depend on the richness of the
location, the number of laborers, and the mining skill of the leader of the group.

A MINE command will only be effective in hilly or mountainous areas. If you give a MINE order in other
locations, you will just waste your time.

The chance of finding a particular metal, and the amount that may be mined depends on the location. In
addition, if a location is rich in a particular metal, then it will remain so throughout the game. However, the
relative richness of a particular location will not be provided to you automatically. You must actually attempt
to mine the location to find out how rich it is, or obtain the information from another player.

These are the items that you may specify in a MINE command:

Gold, Silver, Copper, Iron, or Gems.

Each unit of substance is worth 1 gold, regardless of which substance it is. Thus, the actual weight or
encumbrance of a unit will depend on the substance. In this game, the weight ratios are as follows:

1 unit of gems weighs the same as 1/5 gold.
1 unit of silver weighs the same as 10 gold.
1 unit of copper weighs the same as 100 gold.
1 unit of iron weighs the same as 1000 gold.

For example, 3 copper would have the same weight or encumbrance as 300 gold. In general, one horse can
carry 25000 gems or 5000 gold or 500 silver or 50 copper or 5 iron without slowing down a group while
traveling. See Appendix B for more information about encumbrance.

These substances are like any other items, and can be bought and sold. Some of them can also be used to
build things (see the BUILD command). Note, though, that it makes no sense to buy or sell gold, since it is
the standard and is always traded at exactly one for one.

MOVE [ Table of Contents ]

See the GO command.

NAME [ Table of Contents ]

Use the NAME command to name a low-level subordinate which you have already recruited. Here are some
examples:

Name male soldier Joe Henley.
Have Jema Kendi recruit 1 sailor
and name female sailor Donna Majesti.
Name male sailor Quasimodo and female soldier Mary Anne,
and male worker Lubiki Dan.
Have Doctor Komaso go to Riverton and recruit 1 soldier and
1 worker, and name male worker Jacobi and male soldier
Pelo Rennick.

Note that you must specify the gender of the character.

Each word in a name must start with a letter of the alphabet (A-Z or a-z). Any other characters except
punctuation marks and comment indicators may appear after the first letter. Names must contain at least 8
characters, including embedded spaces, and are limited to a maximum of 32 characters. If you provide a
name with less than 8 characters, the computer will add random characters until it is 8 letters long. If you
provide a name with more than 32 characters, the excess will be truncated.

Names may not contain reserved words that have special meaning to the computer, such as soldier , gold , sail ,
bishop , wood , etc. See Appendix C for a complete list of reserved words.

You may only name a person that you have recruited; i.e., a member of one of the following professions
which is already under your control:

Worker, Soldier, or Sailor.

Once a person has been named, he or she may then be given individual orders, be promoted, become a group
leader, sent on assignments, and so on.

If you want to give a named person a title, simply PROMOTE the person after naming him:

Name male soldier Joe Henley.
Promote Joe Henley to primate.

See the description of the PROMOTE command for more information.

By default, a newly named character has no title.

If you want to convert a named character back to an unnamed character, see the UNNAME command.

NEUTRAL [ Table of Contents ]

See the ALLY, ENEMY, and NEUTRAL command description.

NONCOM and COMBATANT [ Table of Contents ]

Use the NONCOM command to indicate that a character will stay out of combat even if one of your other
characters or allies is attacked. Use the COMBATANT command to undo the NONCOM command. Here are
some examples:

Noncom Trader Joe Flint.
Combatant Bill Fenton and Captain Mike Sanderson.
Noncom Phil Anderson and Sister Lamuniya and Lord Tamasaki.

All characters are combatants by default. Non-combatants will fight only if they are explicitly named in an
ATTACK or CAPTURE order.

These commands are implemented during parsing, and will take effect immediately. They are not queued like
most other orders. Because of this, it is not possible to temporarily declare and then undeclare combat status
within a single set of orders.

OBTAIN [ Table of Contents ]

See the GET command. GET, TAKE, and OBTAIN are synonymous and may be used interchangeably.

OFFER [ Table of Contents ]

There are many independent characters in Spoils of Empire, and your characters will meet or hear of them
frequently. These characters are under the control of the computer. The ones you will meet most often are
well-trained and highly experienced, and will be looking for employment.

Since STUDY and TEACH require considerable amounts of time, you can save this time by recruiting people
who already have the experience you need. If you only need them temporarily, you can DISMISS them when
you no longer need them or assign them to someone else.

To recruit an independent named character, use the OFFER command. Here are some examples:

Offer Bishop Nancy Lopenda 100 gold and have her come to
Pomye.
Have Joe Bellin offer 75 percent of his gold to Engineer Tegwi
Olafson.
Offer 1500 to Wizard Ojibenmi and have him summon 3 dragons
and report.

Note that the word gold is optional. As usual, titles are also optional.

All offers must be made in gold. If you offer anything else, the offer will be rejected by the computer.

You do not have to be in the same location as the offeree to make an offer.

In general, a character will accept an offer if it is at least half of the square of his highest level plus the value
of any items in his possession. For example, a wizard with a horse and a magic skill level of 60 will accept an
offer if it is at least 10 + (60 x 60)/2 = 1810 gold.

If the character accepts your offer, he and everyone and everything currently assigned to him will become
yours to control. You may even give orders to the character on the assumption that he will accept. In the last
example above, if Wizard Ojibenmi accepts the offer, then he will immediately try to summon 3 dragons. If
he rejects the offer, then the SUMMON command will fail.

If the character does not accept your offer, he will give you a reason why, and may suggest that you raise
your offer to something more appropriate.

If you make an offer to a character that is already under the control of another player, he may accept if he
hasn't been paid for a long time. Normally, though, he'll provide some excuse for not accepting the offer. In
either case, the player of the character will not be informed that you made the offer. There will also be times
when an independent character will not accept any offer, no matter how high. In this way, you will never
know for sure if a character is independent or under the control of another player.

You may also make an OFFER to your prisoners, using simple, readily available magic to ensure that they
are sincere if they accept.

If you have more than one offer pending to the same character at the same time, then only the first one will be
used. All subsequent ones will be ignored.

PASSWORD [ Table of Contents ]

If you want to change your password, use the PASSWORD command. Here are some examples:

Password SerendipityDoDah
password "This is a dum password."
password "1234. Who the hell are we rooting for?"

The PASSWORD command may appear anywhere in your orders after you've first provided your old
password.

A password must contain between 8 and 64 characters, including embedded spaces, if any. If it is less than 8
characters, then the computer will generate a random password for you. If it is longer than 64 characters, then
only the first 64 characters will be used.

If a password contains spaces or punctuation, it should be enclosed in double quotes, as in the last two
examples above. In general, it's a good idea to always enclose your password in double quotes.

A password is not case-sensitive. For example, My_Password is equivalent to MY_PASSWORD,
my_passWORD, and so on.

It is extremely important to choose a password that other players cannot guess. If someone else knows your
password, then he or she can submit orders for you. However, you may need to tell your password to a
trusted ally if you will be unable to play the game for a while. When you are able to play again, you can
change your password using the PASSWORD command.

PAY [ Table of Contents ]

It costs money to maintain all of your subordinates. They must be paid on a regular basis, or they may desert
you. If unpaid for too long, they can even leave your service and accept an offer from an enemy.

At the end of each status report, your current debt to your subordinates will also be reported. This value is the
number of gold that you must PAY to completely absolve all of your debts to your subordinates. In addition,

the report will also indicate approximately how many weeks worth of wages are owed. Consider, for
example, the following report from your lead character Bill Dawson:

End-of-turn summary: [debt 502g for 3w]

This means that Bill Dawson owes his subordinates 502 gold in back pay, and that it is equivalent to about
three weeks worth of wages.

To pay your subordinates, use the PAY command. Here are some examples (assume that current debt is 102
gold):

Pay 102 gold. # Reduce balance to zero.
Have Joe Bellin pay 30. # Reduce balance to 72.
Pay 200. # Leave a credit balance of 98 gold.
Pay. # Pay off all debt or as much gold as

you have.
Note that it is possible to have a credit balance. When this occurs, you will see the word surplus in your
leader's report instead of debt.

Also note that the word gold is optional.

If you do not specify an amount to pay, the computer will allocate whatever gold you are carrying up to the
debt owed, but will not create a surplus.

Debt is calculated by the computer at the end of each game week. It will cost you 1 gold every 2 months for
each unnamed level 1 subordinate. This includes not only the actual money given to the subordinate but also
the money needed to maintain weapons and equipment, pay for food and lodgings, and all the additional
overhead required to provide for their needs. Workers will cost only one-fourth of a level 1 character. The
salary of a named character will be 5 gold PLUS the effective level of the character, where the effective level
is the square root of the sum of the squares of all levels. The salary for each named character will be shown
on your status reports.

Your leader is not on the payroll. You only have to pay your subordinates.

Although wages are calculated once per week, subordinates only expect to be paid about once per month.
Thus, they are unlikely to desert you if you owe them less than 5 weeks worth of wages.

POST [ Table of Contents ]

If you have secured a location and would like to post a message at the gates that people can read, then use the
POST command. Here is an example:

John Calensa has just secured Madegi Doy. Joe Flint is there
and is not busy. Have him post the message.
Have Joe Flint post
"Welcome to Madegi Doy. Recruiting is strictly forbidden here
without the express permission of Major John Calensa.".

You may only POST a message in a town that has been secured by one of your characters. The character that
is given the order to post the message must be at the desired location, but does not have to be the person that
actually secures the location. (To have the securer post the message, don't forget to use the adverb
immediately .)

A posting will remain in effect until you no longer secure the location or until you post an empty message:

Have Joe Flint post "".

If a secured location has been posted, then everyone at that location that replies to a QUERY or REPORT
order will also tell you the message that has been posted, if any. Also, when a message is posted or changed,
everyone inside the town or just outside the gates will be notified.

Messages are limited to a maximum length of 256 characters, including embedded spaces. Longer messages
will be rejected.

PRAY [ Table of Contents ]

A character with the skill of religion may pray to his god and request a miracle using the PRAY command.
Here are some examples:

Pray for Joe Flint.
Have Joan of Arc pray for me and Larry Hobart.
Have Friar Tuck pray for himself.
Have Sister Theresa pray for herself.
Have Tuck and Theresa pray for themselves.
Have Bishop Rawlins pray.

Note that you may use the reflexive pronouns myself , yourself , himself , herself , or themselves if the
supplicant is to pray for himself, herself, etc. If no one to pray for is mentioned in the command, then the
supplicant will pray for himself, as in the last example above.

You do not have to be in the same location as the person you are praying for. You may even pray for
characters of other players.

As with all requests for miracles, the chance of success will depend on the amount of religious power that the
supplicant has accumulated, and power may be taken by the god even if the miracle is not granted. If a
supplicant requests a miracle but has no available religious power, then the god may become angry and
punish the supplicant.

If the prayer is granted, then the result will depend on the status of the person you are praying for. For
example, if the person is dead, then he will be resurrected; if badly wounded, then he will probably be healed;
if in good health, then he may be given a skill increase, a skill that he doesn't already have, or he may be
given gold or something else of value. Since the gods are fickle, there is no way to know in advance exactly
what will happen.

The computer will tell you whether the prayer was granted or not, but will not tell you what the god actually
did. Therefore, it's a good idea to have the person prayed for report both before (if alive) and after the prayer
so that you can find out what happened, if anything.

PREACH [ Table of Contents ]

Use the PREACH command to have a religious character preach and otherwise take care of the religious
needs of the people. In the process, he will also collect tithes and donations. Here are some examples:

Have Bishop Jake Henderson preach for 2 weeks.
Preach for 6 days.

If you do not specify the amount of time to preach, then it will be assumed to be exactly one game week = 7
game days.

See the WAIT FOR command for a more thorough discussion of how to use the preposition for.

The amount collected in donations will depend on the religion skill level of the preacher and on the
population of the location.

When preaching, it is also possible for the preacher to attract new followers. Most of the time, these people
will be unskilled (i.e., workers), but occasionally, a skilled individual may join him.

PROBE [ Table of Contents ]

The PROBE command may be used to magically learn more about a character under the control of another
player. Here are some examples:

Probe Hannibal Brunt.
Have Merlinus probe Genghis Khan.

If the PROBE spell is cast successfully, then you will receive a complete report of the target of the spell, and
the target will not know that he has been probed.

It costs 25 magical power to cast a PROBE spell, whether the spell succeeds or not. The spell-caster and the
target do not have to be in the same location.

The basic chance of success as a percentage is simply the magical skill level of the spell-caster. For example,
if the spell-caster has a magic skill level of 82, then the base chance of success is 82%.

In addition, the target will have a chance to resist the spell equal to his effective skill level (the effective skill
level is the square root of the sum of the squares of all skill levels). For example, if the target's effective skill
level is 62, then there is an additional 62% chance that the spell will fail. If the target successfully resists a
PROBE spell, he will be notified that an attempt was made, but he will not know who made the attempt.

PROMOTE [ Table of Contents ]

The PROMOTE command may be used to change the title of a named character. A character must have a
name before he or she may be promoted. Here are two examples:

Promote Jim Thomas to Major.
Have Joe Baker go to Riverton and recruit 1 worker
and name male worker Larriford and promote Larriford to
Doctor.
Promote Joe Smith and Ken Jones to Captain and Mendikompo
to Sorcerer.
Promote me to King and Lousia to Queen.

If you do not want your named character to have any title, then PROMOTE him or her to untitled , as in the
following example:

Promote Jim Thomas to untitled.

The default for newly named characters, including your lead character, is to have no title at all.

You may promote any of your characters (including yourself) to any of the official ranks (see below). A title
is, in effect, simply a label that you want other players to see in their encounters with you. For an untitled
person, no title will appear at all in any reports to you or to other players.

The computer attaches no meaning whatsoever to the titles that you give to yourself or your subordinates.
However, there is a standard that it will apply when naming non-player characters under its control. Here is
the correlation between highest skill level and title:

Skill

Level Combat Sailing Magic Religion

1-9 Soldier Sailor Mage Friar or Sister
10-19 Captain Ensign Conjurer Father or Mother
20-29 Major Mate Sorcerer Bishop
30-39 Colonel Captain Adept Archbishop
40-100 General Admiral Wizard Primate

I highly recommend that players also conform to this standard if you are controlling honest characters.
Obviously, if you wish to deceive others, then use whatever title you want. And you always have the option
of not using any title at all.

There are also special skills that are associated with a single basic title, regardless of skill level:

Skill Title
Engineering Engineer
Mining Miner
Trading Trader

For these skills, you may apply the following modifiers to the actual title, if an actual title is used:

Level Prefix

0-9 Novice
10-19 Junior
20-29 (none)
30-39 Senior
40-100 Master

For example, if you have a character with an engineering skill level of 14, then an appropriate PROMOTE
order would be Promote so-and-so to Junior Engineer.

There are also titles that you may use that are not associated with any skill or skill level:

Mister, Madam, Miss, Mistress, Sir, Dame, Squire, Lady, Lord, Baron, Baroness, Count,
Countess, Duke, Duchess, Prince, Princess, King, Queen, Emperor, Empress, Ambassador,
Doctor
Use one of these (or none at all) if you decide that a normal title is inappropriate for your character.

Finally, since the computer does not attach any value to titles, you can combine titles and modifiers in any
way you wish, no matter how silly or confusing it may be to a human reader. Here are some examples of
perfectly legitimate PROMOTE orders:

Promote Joe Flint to Master soldier.
Promote me to Master Junior.
Promote Lois Park Smith to Trader Bishop.
Promote Mike Bellin to Engineer Engineer.
Promote Merlinus to Sister Wizard.

Note though, that you are only allowed one or two words for a title. If you provide more than two, the
computer will ignore any after the first two.

PURCHASE [ Table of Contents ]

See the BUY command. BUY and PURCHASE are synonymous and may be used interchangeably.

RECHARGE [ Table of Contents ]

See the CHARGE command. CHARGE and RECHARGE are synonymous and may be used
interchangeably.

RECRUIT and HIRE [ Table of Contents ]

Use the RECRUIT/HIRE command if you want yourself or one of your subordinates to hire additional
people. RECRUIT and HIRE are synonymous and may be used interchangeably. Here are some examples:

Recruit 50 soldiers.
Have Jim Thomas hire 5 soldiers and 1 worker.
Have Admiral Lois Park go to Albatross City and buy 1 galley and 40
slaves and recruit 10 sailors.

Have Engineer Domajiki hire 200 workers and go to Plugby and collect
stone for 2 weeks, and then fortify Plugby.

Here is a list of the professions that may be recruited:

Worker, Soldier, and Sailor

As you can see from the above list, you can only RECRUIT low-level characters. These people have at most
a single skill at a skill level of 1. Thus, a soldier has a skill level of 1 in combat and a sailor has a skill level
of 1 in sailing. Workers have no skills at all. If you would like to hire more experienced characters, use the
OFFER command.

It costs 1 gold to recruit each soldier or sailor. It costs one-quarter gold for each worker (round up to the
nearest whole number). For example, if you recruit 3 sailors and 4 soldiers, then you will have to
immediately pay them 1 gold each for a total of 7 gold. If you recruit 5 workers, your immediate cost will be
2 gold.

An attempt to recruit people may not always succeed. In some locations, what you seek may simply not be
available. For example, if you attempt to recruit sailors in a small desert outpost, you will probably fail.

It is also possible that the number of available recruits may be less than what you want. In general, the
availability of people will depend on the location. More people will be available in locations with higher
populations. Also, it may be difficult to find new recruits even in large cities if a large number of people have
been recently recruited there.

Workers are easier to find than the other professions.

If you want to keep trying until you recruit the exact number specified, then place the adverb definitely
immediately before the verb RECRUIT. Here is an example:

Definitely recruit 100 soldiers and 10 sailors.

In the above example, if you find less than 100 soldiers, then you will try again until you succeed. You will
then try to recruit 10 sailors, and will keep trying until you succeed. You can always cancel the order before it
finishes by using one of the HALT/STOP commands.

Instead of a quantity, you may specify a time limit using the preposition for , as in the following example:

Recruit soldiers for 6 days. # Or until I run out of money.

See the WAIT FOR command for a more thorough discussion of how to use the preposition for and the
optional adverb exactly. If you do not use exactly , then the current recruiting session will be completed
before stopping, no matter how long it takes.

Finally, keep in mind that you'll also have to PAY your recruits if you wish to keep them in your service.

REPAY [ Table of Contents ]

See the BORROW command.

QUERY and REPORT [ Table of Contents ]

In this game, information about the current status of your characters (such as skill levels, members of their
groups, their possessions, etc.) or about the location they are in is generally not provided automatically,
except in unusual circumstances. Because of this, if you want this information, you must specifically ask for
it. To do this, use the QUERY or REPORT commands. Here are some examples:

Report.

Report on my current status and location.
Query Bill Johnson and Joe Flint.

Get an immediate report from them.
Have Bill Johnson go to Riverton and report.

I want to know what's going on there as soon
as he arrives.
The report will include the current status of the person reporting, as well as additional information about the
location he is in. The amount of additional information will depend on who he meets and the nature of the
location. For example, in a small outpost, all of the important people there will be listed. In a larger city,
however, where it's much easier to blend into the crowds, only truly notable people or relatively large groups
will be noticed. (Even if you don't actually meet or even see each other, you may hear about other people
from residents of the location.) Finally, the size of the group giving the report will also have an effect on how
much information will be reported. If the reporter is in charge of a large group, then more information can be
obtained.

Here is an example of a report:

Report:
Captain John May (combat 20, magic 25), Adept Carolyn Bond,
39 soldiers, 307 gold, and 41 horses, currently awaiting
orders in Umadosh.
Adept Carolyn Bond (magic 30), 1 horse, 5 gold.
Other notable people in Umadosh (pop. 53000):
Major Billemia, 50 soldiers and 51 horses.
Queen Linda Wandi, Adept Betina, 19 soldiers, and 24 horses.

In the above example, John May is your character and is the person doing the reporting. Carolyn Bond is also
one of your characters but is not actually giving a report - she is simply listed as being in the group led by
John May. Major Billemia and Queen Wandi are either controlled by other players or by the computer.

The QUERY command does exactly the same as the REPORT command, except that it allows the leader to
get a report from a subordinate immediately, even if the subordinate is currently busy doing something else.
For example, consider the following:

Have Joe Flint go to Umadosh and report.
Buy 10 horses.
Query Joe Flint.

As soon as you finish buying the horses, you will ask for and get a report from Joe Flint, even if he is still en
route to Umadosh. In addition, he will send you a second report as soon as he arrives in Umadosh.

It is also possible to get a shorter summary report, instead of the default report, which can be quite long. To
do this, place the adverb briefly before the verb, as in the following examples:

Have Jane Edwards go to Nodim and briefly report.
Buy 10 horses and briefly query Joe Flint and Jane Edwards.

The shorter report will not provide lists of skills or separate descriptions for each named character in the
group. It will also not list other notable people at the location. Here is the brief version of the sample report
shown above:

Brief report:
Captain John May, Adept Carolyn Bond, 39 soldiers, 312 gold, and 42
horses, currently awaiting orders in Umadosh.

Note that the separate listing for Carolyn Bond has been removed, and that her horse and gold have been
added to the total.

It's a good idea to give a REPORT order to yourself and to all of your group leaders for every location they
go to or remain in. Otherwise, the computer will assume that you are not paying attention and have no
interest in the other people that may be in the same location.

Finally, it's important to keep in mind that just because you notice other people does not necessarily mean
that they will notice you.

RELEASE [ Table of Contents ]

See the DISCARD command. DISCARD, DISMISS, FREE, and RELEASE are synonymous and may be
used interchangeably.

SAIL [ Table of Contents ]

Use the SAIL command to have someone travel to a new location by sea. (To travel by land or by air, use the
GO/COME/MOVE/TRAVEL or FLY command.) Here are some examples:

Sail to Sidnaya. # I will sail to Sidnaya.

Assign 100 soldiers and 100 horses to Joe Flint.
Assign Joe Flint to Captain Davy Jones.
Have Davy Jones sail to Madegi Doy and have Joe Flint
attack Ghengis Khan.

The amount of time it takes to travel between locations depends on the distance, the sailing skill of the
captain, and the number of people available for rowing.

Distances can be determined by looking at the map provided by the Gamemaster.

When sailing to a location, it is possible that another player may be in control of the location (see the
SECURE command). If so, your party may be denied access. If this occurs then the travelers will remain
outside the gate/walls.

There may also be times when you intentionally wish to remain outside the gate/walls. If so, use the word
outside between to and the name of the location. Here is an example:

Have Joe Flint sail to outside Madegi Doy.

If you want to remain near the location, but far enough away that you cannot be seen from within or just
outside, then use the word near , as in the following example:

Sail to near Madegi Doy.

The person given the SAIL order is assumed to be the ship's captain, and must have a sailing skill of at least

However, a person with such a low skill level is likely to take a considerable time to reach the destination.
The greater the skill level, then the sooner the arrival.
A galley must also have at least 10 (unnamed) sailors to perform the various tasks needed for the proper
functioning of the ship. A ship with fewer sailors will take much longer to reach its destination.

A galley requires at least 40 rowers (in addition to the 10 required sailors) to make maximum headway. If
fewer than 40 rowers are available, then the sailors will depend more on the use of sails, and the trip will take
longer. No special skills are needed to row, and anyone other than the captain and the 10 required sailors will
be used for this task (including other sailors, workers, religious people, soldiers, slaves, and so on, but
excluding elite troop units who will continue training while onboard).

See Appendix B for information on how much a galley can carry without overloading.

When there is more than one named location between the starting point and the destination, the computer will
determine the fastest route to go by.

The computer will reject any SAIL order if there are no sea routes linking the initial and final locations. If
you wish to travel by both land and sea, then issue separate GO/COME/MOVE/TRAVEL and SAIL orders.

SAY and TELL [ Table of Contents ]

Use the SAY or TELL command to give a message to another player. Here are some examples:

Go to Kitesta and tell John May "Here's the gold I promised you.",
and give him 100 gold.
Have Joe Flint say "Not on your life!" to King Bodo Bunji and
Nebuchadnezzor.
Have Kalistoga tell Empress Maudline
"My liege lord asks me to give you this message.
If you will free your prisoner Nancy Morrow then he will
immediately remove all of his troops from Madegi Doy and
Plugby. Please reply to this message as soon as possible."

A message must be enclosed in double quotes and is limited to a maximum of 2500 bytes (about 1 full page
of dense print).

Note the difference between SAY and TELL. With SAY, the name of the recipient must follow the
preposition to which, in turn, follows the message. With TELL, the order is reversed and the proposition to is
not used. In other words, the word order is exactly the same as grammatically correct English.

A character may give a message to any other character. If they are not in the same location, then inexpensive
and readily available magic will be used to transmit the message.

It is also possible to broadcast a message to everyone in a city or town. To do this, simply use a town's name
instead of a person's name.

It is also possible to broadcast a message to everyone on the planet (i.e., to all players in the game). Again,
there is no cost for this. To broadcast a message, use the pronoun everyone as in the following examples:

Tell everyone "Emperor John May has declared himself ruler of
the entire world! Fear and obey him or face his wrath!"

Say "Emperor John May now rules the world!" to everyone.

If you send a message to one of your prisoners, then the prisoner's player will receive the message.

The computer will remove all tabs from messages. Thus, you may use tabs to make your orders more
readable. However, do not use any complex formatting in your messages (such as columns, tables, special
indenting, and so on), because the computer will reformat the message to comply with the normal status
report. If you use complex formatting, the result may not be what you intend.

SCAN [ Table of Contents ]

Use the SCAN command if you possess a magical orb and want to use it to get a report of a distant location
where you have no subordinates.

Here are some examples:

Scan Madegi Doy using Hanemishi.
Have Merlinus scan Kitesta and Pritwa Fas with Anomba.
Scan Plugby and Irontown using Jamibo and Tashendi
using Akitemba.

Note that you must specify the name of the orb after the word with or using.

If the orb has sufficient power to cover the distance to the location, then the power will be subtracted and a
report of the location will be provided. However, unlike the REPORT/QUERY commands, a report of a
location is complete when using an orb, and all people of note at the location will be detected.

An orb will only tell you who is inside or outside a town or city. It cannot be used to scan people near the
town.

See also the PROBE command.

SEARCH and EXPLORE [ Table of Contents ]

If you wish to explore an uninhabited location with the hope of finding something of value, then use the
EXPLORE/SEARCH command. EXPLORE and SEARCH are synonymous and may be used
interchangeably. Here are some examples:

Go to Hakkaba and search.
Have Joe Flint and Bill Digby explore for 45 minutes.
Search for 7 days.
Have Mike Fenton explore for 3 weeks.

Do not specify the location to explore. The computer will always assume that the person given the order will
search in his current location.

You must be inside the boundary of an uninhabited location if you wish your search to be successful. If you
are outside or near the location, or if the location is permanently inhabited by humans, then you will not find
anything. (On the map, searchable locations are marked as "uninhabited ruins".)

If you do not specify the amount of time to search, then it will be assumed to be exactly one game week = 7
game days.

See the WAIT FOR command for a more thorough discussion of how to use the preposition for.

Uninhabited ruins are uninhabited only in the sense that humans do not live there. Quite often, however,
these locations are the lairs of unsavory creatures such as orcs and goblins, or even more powerful creatures
such as demons and dragons, and there is always a chance that they will not appreciate your visit. Keep this
in mind.

There is no way to predict what you will find, if anything at all. However, people who search ruins are
generally looking for powerful magical items, not gold or gems, since monsters rarely have enough wealth to
be worth the risk.

SECURE [ Table of Contents ]

If you want to take complete control of a location and automatically tax it to the maximum degree possible,
then use the SECURE command. Here are some examples:

Secure Madegi Doy.
Have Joe Flint go to Kitesta and secure it for 30 days and then go
to Benkamu.
Go to Tashendi and secure.

Note that the name of the location or the pronoun it is optional but may be included for readability. The
computer will ALWAYS assume that the location of the character when the command is executed is the
location to secure, even if you specify a different location.

A SECURE order will fail immediately if the location is already secured by another character, even if he is
one of your own, and regardless of your relative strengths. If you want to take over a location from another
player, then you must attack them and force them to retreat (see the ATTACK and CAPTURE commands).

If you want more than one group to secure a location, then first combine them into a single group.

A secured location is automatically taxed by the group that has secured it, and all available taxes are
collected. There is no need to have other subordinates TAX the same location (in fact, such an attempt will

fail).

A SECURE order will remain in effect until the person given the order is given a HALT or STOP order, or
until he is attacked by another player and either forced to retreat from the location or is weakened sufficiently
to prevent him from maintaining security. It will also terminate if modified by an until or for phrase:

Have Joe Flint secure Kitesta until 12:00 July 17, 1150.

A SECURE order will only succeed if you have sufficient military strength to control the entire location. In
general, you will need a minimum of 1 soldier per 25 population to completely secure a location. This
number will be reduced somewhat if the location is fortified (see the FORTIFY command).

If you have more than enough people to secure a location, then any excess people will automatically WORK.
In this case, any people in the group that are not actually securing the location (including named and
unnamed characters, but not elite troops) will work as common laborers.

If a location is secured, then armed characters controlled by another player may not be allowed to enter the
location by means of the GO or SAIL command if the total number of his people already at the location is at
least 1 percent of the population. An armed person is anyone with a combat skill level greater than zero.
Instead, people refused entry will be required to remain outside the city/town limits. However, people may
always FLY or TELEPORT into a location, whether or not it is secured.

If forces of other players were already in the location when it was secured, they will not be allowed to TAX
the location, although they will be allowed to leave.

If characters of another player are attacked in a location that you have secured, then you will automatically
aid the defenders. This will only occur if the attack in within the town/city walls. If a battle occurs outside the
walls, you will not automatically intervene, but you will be notified of what happens.

SELL [ Table of Contents ]

Use the SELL command to sell items to the general public. Here are some examples:

Sell 1 galley and 40 slaves and Galiponita.
Give Joe Flint 25 horses and have him go to Tashendi and
sell 25 horses.
Go to Kitesta and definitely sell 40 copper and 25 silver and
all except 2 wagons.
Have Trader Kim Daniels buy 10 horses and 1000 copper
and go to Tashendi and sell 10 horses and 1000 copper.

The person doing the selling will try to sell the items for the best price possible. Characters with high levels
of trading skill should be able to sell at a profit.

You may not use the SELL command during character generation.

Instead of a quantity, you may specify a time limit using the preposition for , as in the following example:

Sell horses for 6 days. # Or until I run out of horses.

See the WAIT FOR command for a more thorough discussion of how to use the preposition for and the
optional adverb exactly. If you do not use exactly , then the current sale will be completed before stopping.

In all other respects, the SELL command is the exact opposite of the BUY/PURCHASE command. See the
description of BUY/PURCHASE for more information.

STOP [ Table of Contents ]

See the HALT command.

STUDY [ Table of Contents ]

Use the STUDY command to learn new skills or increase existing ones. Here are some examples:

Go to Ocean City and study sailing.

Study sailing skill for 1 week.
Have Mike Jones study magic and sailing.

Study magic and sailing skills for 1 week each.
Skill levels range between 0 and 100. If you attempt to increase a skill beyond 100, the attempt will fail.

A skill level is described by two numbers: an effective level and a partial level. For example, a mage might
have a magic level listed as 14.11. This means that his effective magic level is 14 and that his partial level is
11; i.e., he has accumulated 11 points towards the next level. When the partial level reaches the NEXT
effective level, the effective level will be increased by one and the partial level will start again at zero. For
example, when the mage reaches 14.15, it will automatically change to 15.0.

It costs exactly 1 gold for each week of study. The actual rise in the skill level is random, and can vary from 1
to 5 partial points.

Even though the computer keeps track of partial levels, you may not use them in the command itself. You
must always use whole numbers; anything after a decimal point will have no effect. For example, the order
Study magic to level 16.5 will be equivalent to Study magic to level 16.

When you actually use a skill, only the value to the left of the decimal point will apply. For example, if you
cast a spell and your magic skill level is 79.79, then you will cast it at level 79, not at level 80!

If you want someone to study a skill for more than 1 week, use the preposition for and state the number of
weeks to study. Here are some examples:

I will study combat for 3 weeks.
Study combat for 3 weeks.

I want Joe to study magic for 1 week in Riverton.
Have Joe go to Riverton and study magic for 1.

Note that the word week(s) is optional.

If you want someone to increase a skill to a specific level, you should use the preposition to , as in the
following examples:

Increase magic skill to level 7.
Have Joe Smith study magic to level 7.

Increase my magic level to 20 and my combat level to 14.
Study magic to 20 and combat to level 14.

Have Joe increase combat to level 41 and sailing by one point.
Have Joe Smith study sailing and combat to level 41.

Note that the word level is optional.

Note in the last example, that Joe Smith will study sailing for one week - and not until his skill rises to 41. If
to or for plus a number does not appear directly after the skill name, then it is assumed that the character will
study for exactly one week.

This option (using to ) is especially useful during character generation. During actual game play, for will be
much more useful.

An attempt to STUDY may not always succeed. In some locations, a suitable teacher may simply not be
available. For example, if you attempt to study sailing in a small desert outpost, you will probably fail. In

general, heavily populated locations are more likely to have teachers with the skills you need.

SUMMON [ Table of Contents ]

To have a spell-caster summon powerful magical creatures, use the SUMMON command. Here are some
examples:

Summon 2 dragons.
Have Merlinus summon 1 demon and 2 griffins and join Joe Flint,
and then have him attack Genghis Khan.

The magical power needed to summon a magical creature depends on the creature, as follows:

Skeleton 1
Zombie 2
Harpy 5
Minotaur 10
Griffin 20
Chimera 30
Dragon 40
Demon 50

For example, to summon 2 minotaurs and 1 dragon would require 2 x 10 + 40 = 60 points of magical power.

A summoned creature will remain with the spell-caster for a number of days equal to the spell-casters skill
level in magic when the spell was cast. At the end of that time, they will return automatically to the elemental
plane. They may also be dismissed by using the DISMISS command at no cost in magical power (e.g., Have
Merlinus dismiss all his dragons ).

You will be notified in your status report when griffins, chimeras, dragons, and demons return to the
elemental plane. You will not be notified when skeletons, zombies, harpies, and minotaurs disappear.

Summoned creatures must remain with the spell-caster that summoned them. They may not be re-assigned to
someone else.

In combat, summoned creatures are not only fearsome fighters and very hard to kill, but they also instill fear
into the opponent, which can provide a significant advantage.

Summoned creatures have no encumbrance for the purposes of the FLY, GO/COME/MOVE/TRAVEL, or
SAIL commands. They always travel under their own power and will not hinder the progress of the people
they travel with.

While summoned creatures may not be directly teleported, the spell-caster who controls them may teleport
himself or be teleported by someone else. When this occurs, the summoned creatures have zero encumbrance
and no extra magical power is needed to teleport them.

SUPPORT [ Table of Contents ]

If you want to fight alongside an ally when he attacks, use the SUPPORT command. Here are some
examples:

Support Joe Flint and Nancy Ramirez.
Have Luke Anderson support Hannibal for 2 months and then tell me
"I'm done supporting Hannibal. What do you want me to do now?".
Have General Toby Tyler go to Pomye and support Fidoskank for 9
days and then go to Yakaboti and explore.
Have Mike Saunders and Taikh ibn-Shuduuf go to Umadosh and support
Genghis Khan until 12:00 May 5, and then come to Tashendi and join
me.

In the last example above, Mike and Taikh will support Genghis Khan if and when he attacks someone else.
If this occurs, they will fight alongside him as if they had given the same ATTACK/CAPTURE order at
exactly the same time.

However, separate groups fighting together will not be as effective as a single combined group under a single
leader because combat leadership and religious impact are limited to a single group. For example, Mike
Saunder's leadership ability will have a multiplicative effect only on his own group. It will have no effect on
the combat effectiveness of Genghis Khan's group.

If you do not specify a time limit with a for or until phrase, then the person will continue to support the
named individual(s) until given a HALT or STOP order.

See the WAIT FOR command for a more thorough discussion of how to use the preposition for.

While a person is supporting someone else, he and his group will simultaneously WORK. Thus, no one will
waste any time twiddling their thumbs.

TAKE [ Table of Contents ]

See the GET command. GET, TAKE, and OBTAIN are synonymous and may be used interchangeably.

TAX [ Table of Contents ]

If you want the people in a location to pay you taxes, then use the TAX command.

A character that is given a TAX command will attempt to collect taxes in his current location for the number
of days specified. Here are some examples:

Tax for 2 weeks.

I (and all the soldiers in my group) will tax the
people in my current location for 14 days.
Assign 200 soldiers to Captain Bill Jones.
Have him go to Riverton and tax for 3 weeks, and go to
Ennistown and tax, and go to Hampton and tax for 3 days and
go to Bindy Village and tax for 12 hours.

If you do not specify the amount of time to collect taxes, then it will be assumed to be exactly one game
week = 7 game days.

See the WAIT FOR command for a more thorough discussion of how to use the preposition for.

You may not TAX a location that is currently secured by another character, even if it is one of your own
subordinates. See the SECURE command for details.

The amount of time required to collect taxes from the entire population of a location will depend on the
population and the number of soldiers collecting the taxes (workers and sailors do not collect taxes). The
amount of taxes collected will depend on the population of the location and on how long it has been since the
people in that location were last taxed.

A location generates about 1 gold per 4 residents per year in taxes. For example, a location with a population
of 40,000 will generate a total of 10,000 gold in taxes per year. However, available taxes never accumulate
beyond 30 days. Thus, if you want to collect as much taxes as possible, then a location should be taxed at
least once a month.

As a general rule-of-thumb, it will take about four daylight hours to extract all available taxes in a location if
the number of soldiers is equal to the total population of the location. (In this game we assume that a day has
about 12 daylight hours.) For example, if a group has 500 soldiers, then it will take them approximately 320
daylight hours (about 27 days) to thoroughly tax a location with a population of 40,000.

A simpler way of looking at it is that each soldier, on average, can collect a maximum of about 1 gold every
four days, assuming that the location has sufficient population to generate taxes at this rate, and that the
location has not recently been taxed by someone else.

If you do not want your soldiers to completely tax a location, then use one of the HALT/STOP commands
(whichever is more appropriate). The amount of taxes actually collected will be proportional to the amount of
time between start and stop. (More specifically, taxes are generated once each game day).

If more than one group is collecting taxes in a location at the same time, then the taxes will be allocated in
proportion to the number of soldiers collecting the taxes in each group.

When a location is taxed, any other players with characters in the same location will be notified when the
taxing begins, when it ends, and who is doing it. Anyone that is just quickly passing through will usually not
be notified.

TEACH [ Table of Contents ]

If you want one of your subordinates to teach a skill to another subordinate, then use the TEACH command.
Here are some examples:

Have Joe Flint teach combat to Carolyn Bond to level 7.
Teach Mike Fenton magic and combat.
Have Bishop Yemishambi teach Sister Linda Bayer religion
for 2 weeks and religion to Friar Tuck to level 3.

The teacher must have a skill level at least as high as is being taught and may teach only one student at a
time. For example, the order Teach magic to Linda Bayer and Joe Flint will fail.

The TEACH command has exactly the same effect as the equivalent STUDY command. The only difference
is that there is no cost because you are providing the teacher. Also, a high level teacher is likely to be able to
teach more in the same amount of time.

See the STUDY command for more details.

TELEPORT [ Table of Contents ]

Use the TELEPORT command to magically transport a character and everyone and everything in his group to
a different location. Here are some examples:

Assign 10 soldiers and 10 horses to Joe Fenton, and have
Majisto teleport him to Kitesta.
Have Circelina and Merlinus teleport themselves to Plugby.
Teleport Mike Flint and Sandy Wheaton and yourself to
outside Tashendi.
Have Merlinus teleport to near Madegi Doy.

Merlinus will teleport himself and everyone/everything
in his group.
If the TELEPORT command is immediately followed by the preposition to , then the magic user will teleport
himself, as in the last example above. You may also use an appropriate reflexive pronoun, as in Teleport
yourself to Kitesta or Have Circelina teleport herself to near Pritwa Fas. (Note that themselves in the
second example above is optional.)

If you want to teleport to a location just outside the gates/walls of a town or city, then use the word outside ,
as in the third example above. The default is to teleport inside the location. You may also teleport to an area
that is near the location but not visible from within or just outside by using the word near.

A spell-caster must have a magic skill level of at least 25 to use the TELEPORT command.

The amount of magical power needed to teleport a person and his group is equal to the total encumbrance of
the group (rounded up to a whole number). See Appendix B for encumbrance values of people and items.

The amount of time needed to cast a teleportation spell also depends on the encumbrance of the group being
teleported.

The TELEPORT command has no limit on distance. As long as the spell-caster has sufficient power to handle
the encumbrance, he may teleport to anywhere on the planet.

An attempt to TELEPORT one of your own characters or a character of a player that has declared the spell-
caster an ally will always succeed (assuming, of course, that the spell-caster has the ability, the power, and is
in the same location as the person being teleported). You may also attempt to teleport a character that is
someone else's prisoner.

It is also possible to TELEPORT a character of another player. However, the chance of success in casting the
spell will be the caster's magic skill level. This chance will be reduced somewhat depending on the number of
people in the victim's group. For example, if you attempt to teleport a lone enemy and your magic skill level
is 36, then there is a 36% chance that you managed to cast the spell without the victim being aware of it. (If
he were aware of it he could simply walk away and spoil the spell. If he is a prisoner and his captors notice
you, then they will also be able to spoil the spell.) If the target is part of a group, then the success chance will
be reduced based on the number of people in the group. Specifically, the percent reduction will equal the
square root of the number of people in the target's group. For example, if the above target were part of a
group with 400 people in it, then the success chance would be 36 - (20% of 36) = 29% (rounded).

In addition, if you are not noticed, there is still a chance that he can resist the spell after you've cast it. This
chance is equal to his magic skill level or HALF of his highest non-magic skill level, whichever is higher.
For example, if you successfully cast the spell without being noticed and his magic level is 71, then he will
have a 71% chance of resisting and spoiling the spell. If you try to TELEPORT a prisoner of another
character, he will never try to resist, even if he is someone else's subordinate.

If an attempt is spoiled or resisted, the spell-caster will still expend the magic power needed for the spell.
Also, subsequent attempts against the same target in the same processing session will fail, even if the
attempts are made by different spell-casters. Thus, it does not make sense to give multiple TELEPORT orders
targeted at the same enemy or prisoner.

In addition, if an attempt is spoiled or resisted, and if the target's group is significantly stronger than the spell-
caster's, then the spell-caster's group will be captured by the target's group and made prisoners, unless the
spell-caster can immediately escape by teleporting himself (and his group, if any) to a random location. The
chance of successfully evading capture will be the spell-caster's effective magic level. If the spell-caster does
not have enough magic power to teleport away, then he will be captured.

Finally, when teleporting an unsuspecting character (i.e., a character of another player that has not declared
the spell-caster an ally), only small personal items (gold, silver, gems, and magical items) and summoned
creatures will be teleported with the target. Anything larger will be left behind, and sufficent magical power
will be needed only for the person being teleported and his small personal items.

TRAIN [ Table of Contents ]

Instead of directly recruiting soldiers and sailors, you also have the option of training workers to become
soldiers or sailors. You may accomplish this by using the TRAIN command:

Take 10 workers from Mike Hansen and 10 workers from Joe Flint and
train 20 soldiers.
Have Admiral Bill Cunningham train 40 sailors.
Go to Kitesta and definitely recruit 30 workers and train them.
Have Genghis Khan train soldiers.

If you do not specify an actual number to train (as in the last example above), then the computer will assume
that you want to train all the workers in the agent's group. If you simply say "train them" as in the third

example, then the computer will assume that you want to train soldiers.

A trainer must have an appropriate skill level (combat to train soldiers and sailing to train sailors) of at least
10 in order to be a trainer.

The time needed to train is based on the assumption that a level 50 trainer can train 5 workers to level 1 in 1
week. Any other combinations will have proportional results. Thus, the amount of time needed to train (in
days) is 70 times the number of trainees divided by the skill level of the trainer. However, the minimum
training time will never be less than 1 week.

TRANSFER [ Table of Contents ]

Use the TRANSFER command if you want one character to transfer funds to another via the banking guild.
Here are some examples:

Transfer 200 gold to Billy the Rat.
Have Jim Fielding transfer 75% of his gold to Hanna Lando.
Transfer all but 50 gold to Trader Philippe Olivier.

The banking guild charges a fixed fee of 10 gold plus one percent of the amount transferred, rounded up. For
example, if you wish to transfer 140 gold, then it will cost a total of 140 + 10 + 2 = 152 gold. If the sender
does not have the full amount needed, then the transfer will fail.

WARNING!
The amount to transfer is determined first and the fee is added to it. For example, if you
have 200 gold and transfer "all but 50 gold", then 150 will be transferred and the fee will
be 12 gold, leaving you with just 38 gold.
The banking guild has offices inside every inhabited town or city. If you attempt to transfer funds from an
uninhabited location or from outside or near a town, then the transfer will fail. The location of the recipient
does not matter.

The guild actually transfers the money using a magical teleport spell. Thus, if the bank office is in a magic-
free area, the TRANSFER command can not be used!

TRAVEL [ Table of Contents ]

See the GO command. GO and TRAVEL are synonymous and may be used interchangeably.

UNLOAD [ Table of Contents ]

If you need to move a character out of his current group (making him a group leader) without giving him a
direct order, use the UNLOAD command. Here is a useful example:

Mike Ross needs to recruit soldiers in Tashendi, but it is
currently secured by Tom the Rat, and Mike won't be allowed
to enter with all of his soldiers. So, have him give his
soldiers to Joe Flint who will wait outside.
Have Mike Ross get Joe Flint and go to outside Tashendi and
unload Joe Flint and give him all his soldiers.
Then have Mike Ross go to Tashendi and definitely recruit 100
soldiers, and go to outside Tashendi and get Joe Flint, etc.

Obviously, you can always make a character a group leader by simply giving him an order. However, the
UNLOAD command is useful when you simply want a character to become a group leader and not do
anything else.

UNLURK [ Table of Contents ]

See the description of the LURK command.

UNNAME [ Table of Contents ]

If you no longer need a named character, you can convert him back to an unnamed character by using the
UNNAME command. Here are some examples:

Unname Joe Flint.
Assign Billy Bob to me and unname Billy Bob.
Have Charles Dickens give 5 gold and 1 horse to Mike Felton
and join Mike Felton and have him unname Charles Dickens.

When a character is unnamed, he is converted to a common worker with no skills.

A character must be part of a group before being unnamed, and must not have anyone or anything assigned to
him. The new unnamed character will be assigned to the group leader. For example, if Captain Bogoshine is
part of General Tandemar's group when he is unnamed, then Tandemar will gain 1 worker.

Note in the last example above that Charles Dickens first transfers everything in his group to Mike Felton
before joining Mike Felton's group. As a final act, he has Mike Felton unname him. In this way, the
unnaming will take place only after the previous commands have been accomplished. Note though, that
Charles Dickens cannot unname himself, since attempting to do so would automatically make him a group
leader immediately before he tried to unname himself.

If you wish to completely eliminate yourself from a game, then you should UNNAME your lead character. In
this case, it does not matter if he has anyone or anything assigned to him. See also Quitting the Game

WAIT FOR, AWAIT, and WAIT UNTIL [ Table of Contents ]

Use the WAIT FOR or AWAIT commands if you want to wait for a specified period of time or if you want to
synchronize the activities of two group leaders. WAIT FOR and AWAIT are synonymous and may be used
interchangeably. Here are some examples:

Wait for 3 days and go to Madegi Doy.
Have Jim Fenton recruit every soldier and wait for 2 weeks and
then go to Salem.
Wait for 1 hour and attack Mike Hanson. # Give him time to leave.
Fly to Londanum and wait for Jonipikoma and wait for 1 hour and
then fly to Ashby.

He'll be waiting for me. Give him a little time to give me the
gold he promised.
You may specify the time period in minutes, hours, days, weeks, or months, as shown in the above examples.
However, you may not combine time units, and the minimum total time is one hour. If you need to specify a
non-integral time unit, then express it in terms of a smaller unit. For example, you can express 1 hour and 30
minutes as 90 minutes or 1 day and 3 hours as 27 hours.

Keep in mind that 1 month in Spoils of Empire is exactly 30 days.

You may also have someone wait for someone else. Here is an example:

Have Dramidias go to Plugby and mine silver for 6 days
and then go to Madegi Doy.
Sail to Madegi Doy and wait for him, and then assign him
to me and sail to Benkamu.

In the above example, you will not leave Madegi Doy for Benkamu until Dramidias has arrived there and
joined you. If he was already there when you arrived, then you will not have to wait at all.

The WAIT FOR/AWAIT command may not be used when the person you are waiting for is just passing
through. Here is an example:

I am currently in Nandigwa and Joe and Mary are currently in
Umadosh, which is on the road between Nandigwa and Tashendi.
Have Joe Flint and Mary Halliday await me and then join me.
Go to Tashendi and attack Larry Dawson.

The above example will not work because the leader is moving, and people may not wait for a moving target.
Instead, here's one way that will work:

Go to Umadosh and wait for Joe Flint and Mary Halliday,
and get them, and then go to Tashendi and attack Larry Dawson.

In other words, you must explicitly stop in Umadosh if you want to pick them up.

When a WAIT FOR order fails (because the two people are not in the same location), it re-schedules itself to
check again in 4 hours. Because of this, there can be as much as a 4-hour delay before the two people become
truly synchronized.

If you cannot structure a command without using WAIT FOR, then always have the person passing through
do the waiting, as in the last example above. You should never wait for a moving person, unless you can
guarantee that he will be there for at least 4 hours.

You may also WAIT FOR more than one person, as in the following example:

Have John Carpenter wait for Bill Fenton and Lois Park, and then
get them and go to Kitesta.

In the above example, John Carpenter will first wait for Bill Fenton. As soon as Bill arrives (or if he was
already there), John will then wait for Lois Park. He will then add them to his group and proceed on to
Kitesta. (Obviously, you should not give Bill Fenton other orders while John is waiting for Lois Park! If you
do, the results may not be what you expect. The computer will not check to make sure that Bill Fenton is still
there when Lois Park arrives.)

You may also order characters to wait until a specified time using a WAIT UNTIL order. Here are some
examples:

Wait until 5:16 March 5, 1149.
Have Joe Flint wait until 17:00, July 27.

Assume waiting starts on December 29, 1152.
Have Mike Anderson wait until 09:30, Jan 2. # Year will be 1153.

The time, month, and day must be specified. The year is optional. If the year is not specified, then the current
year is assumed. However, if the resulting date has already passed, then the following year is assumed.

IMPORTANT!
If you specify a time that is more that 10 years in the future, then the result will be
unpredictable!
In Spoils of Empire, each month has exactly 30 days. Thus, a year has 360 days. This makes the WAIT
UNTIL command easier to use, and avoids the potential confusion caused by leap years.

You can use either the full name of the month or the 3-letter abbreviation. Minor spelling errors will be
detected if you spell the month out in full. No spelling errors are allowed if you use a 3-letter abbreviation.

WORK [ Table of Contents ]

Use the WORK command to have a character and his group (if any) work for wages. Here are some
examples:

Name male soldier Henry Dorn.
Assign 100 soldiers to him and have him go to Tashendi
and work for 14 days.
Have Mike Foster work. # Mike and his group will work for 1 week.
Have Billy Bob work for 10 weeks.
Work for 18 hours.

If you do not specify the amount of time to work, then it will be assumed to be exactly one game week = 7
game days.

See the WAIT FOR command for a more thorough discussion of how to use the preposition for.

The WORK command is primarily intended for low level characters who do not have sufficient skill to
perform more skilled tasks and who are not needed for other, more specific jobs (such as taxing, guarding,
mining, building, and so on). When WORK is used, the person named and anyone in his group will do
whatever work they can find for the normal wages of common laborers.

The amount of wages obtained by working will depend on the population of the location. It is easier to find
work in heavily populated areas. In lightly populated areas, you may not be able to find any work at all. If
your characters cannot find work for pay, then they will do voluntary community service.

In addition, high level characters will try to sell their skills and earn more gold than they otherwise would at
common labor. The chance of successfully doing this will depend on the individual. (High level characters
will be in greater demand than low level ones.) Prisoners in the work group will be much less likely to do
anything other than common labor.

APPENDIX A: CHARACTER GENERATION - YOUR FIRST TURN [ Table of Contents ]

In your first turn, you must submit orders to tell the computer what password you will use in the future. You
will also need to create your lead character; i.e., the character that you should think of as representing
yourself. (In fact, when I say you , I generally mean your leader or your lead character .) You must decide
what his name will be, what title you want him to have (if any), and what items you want him to start the
game with. In deciding what his possessions will be, you will have a certain amount of gold to spend. Here
are the commands that you must submit:

Password "whatever you want"
Gender leader name

The PASSWORD command must be the first command. The LEADER command must be the second
command, and the gender of the leader must be specified as either male or female. Other commands may
follow in any order.

Each player starts the game with 1500 gold, and you may spend the money any way you wish to flesh out
your leader and his subordinates. Here is an example:

Password "Happy days are here again"
Male leader Bill Hayamoto

Go to Ostrina'o. # Start the game here.

Study magic to level 24. # Maximum cost = 24 * 25 / 2 = 300
Recruit 16 workers. # Cost = 16 / 4 = 4
Buy 17 horses. # 1 horse for each of us.

Cost = 170.
Name female worker Tuckitina.

Give her 55 gold.
Have her study religion # I want a priest in my group.
to level 10. # Maximum cost = 10 * 11 / 2 = 55

Name male worker Jim McCoy.
Give him 54 gold.
Have him study magic for 54 weeks.

Promote Jim McCoy to Conjurer and Tuckitina to Mother.

Give 1 horse to Jim McCoy and have him go to Lusa Moch.
Give 1 horse to Tuckitina and have her go to Ochoani.

They can report on conditions near Ostrina'o.
ZZZ

Note that the maximum cost to achieve level N is simply N x (N+1) / 2. Keep in mind, though, that this is the
maximum cost, and assumes that you will rise only 1 partial point per week of study. Since the actual rise
per week is anywhere between 1 and 5 partial points, the actual cost to achieve level N will almost certainly
be less, and your character will still have some gold left after he finishes studying.

After the above orders are processed, you will receive a report telling you the status of all of your characters,
and providing you with information about their location(s).

If you want your characters to start the game in specific locations on the map, then make sure that you
include one or more appropriate GO orders, as in the above example. If you do not specify any GO orders,
then the computer will try to choose a location that has reasonably good growth opportunities and which is
not currently dominated by other players. Note that this applies only if you enter an ongoing game. If you are
entering a brand new game, you should always specify your start location(s).

During character generation, there are no limits on what you may buy, recruit, or study, as long as you do not
spend more gold than you have. The only exception to this is that you may not recruit soldiers. You may,
however, recruit as many workers and sailors as you wish.

Keep in mind, though, that future opportunities for purchase, study, recruiting, and so on will depend on
where you and your subordinates are located. For example, in the next turn, if you are not in a location where
there are magic teachers, then you will not be able to study magic. Only during character generation are your
opportunities unlimited.

IMPORTANT!
When you send in your character generation orders, make sure that you set the email
subject line to "SOE New Player". If you do not do this, there may be a 4-5 day delay in
processing your orders.
All orders that you email to the Gamemaster must be plain text. Multi-part messages in
MIME format, HTML or MS Word documents, or any messages that contain binaries or
attachments CANNOT BE PROCESSED!
Be careful when naming your characters. Keep in mind that a name must have at least 8
characters in it, including embedded spaces.
REMEMBER: You may not recruit soldiers during character generation!
Also, make sure that you PROMOTE your leader if you wish him to have a title. The default is a person with
no title. You may also wish to promote your other named characters.

During character generation, you may use any commands except the following:

ATTACK, BORROW, BUILD/CONSTRUCT/MAKE, CAPTURE, COLLECT/GATHER,
CONJURE, FORTIFY/UNFORTIFY, HALT/STOP, INTERROGATE, KILL/EXECUTE,
MINE, PREACH, SAY/TELL, SEARCH/EXPLORE, SECURE, SELL, SUPPORT, TAX,
TEACH, TELEPORT, TRAIN, WAIT FOR/AWAIT, (WAIT) UNTIL, and WORK

In addition, any REPORT or QUERY orders will be ignored. Instead, during character generation only, a full
report will be automatically generated for each named person in your command after processing your orders.

APPENDIX B: ITEM CHARACTERISTICS [ Table of Contents ]

Basic Production
Item Cost Encumbrance Command

Character N/A 1 N/A

Armor 5 1/5 BUILD
Battering Ram 50 10 BUILD
Catapult 20 4 BUILD
Galley 1000 N/A BUILD
Siege Tower 100 20 BUILD
Wagon 5 10 *** BUILD
Weapon 5 1/5 BUILD

Horse 10 2 *** N/A
Slave 5 1 N/A

Iron 1 1/5 MINE
Copper 1 1/50 MINE
Silver 1 1/500 MINE
Gold 1 1/5000 MINE
Gem 1 1/25,000 MINE

Stone 1 1 COLLECT
Wood 1 1 COLLECT

*** When traveling on land, a horse has no encumbrance. When on
a ship or flying or being teleported, it has the listed
encumbrance. For wagons traveling on land, only the number
that exceeds the number of horses will have encumbrance.

When refering to battering rams or siege towers in your orders, you may also use the single words ram or
tower. For example, Build 3 towers is equivalent to Build 3 siege towers.

Basic costs are the amount of gold that an individual with no trading skill will pay for the item when
purchasing it.

[Stone used for construction is about four times as dense as wood. However, because it is much more difficult
to quarry stone than to cut down trees, the value of wood is about one-quarter the value of stone per unit
weight. Thus, one unit of stone has the same weight or encumbrance as one unit of wood, even though the
volumes are different.]

A galley can carry a total encumbrance of 550 without overloading. If overloaded, the chance of being lost at
sea will be equal to the percent that it is overloaded per each 250 miles traveled. For example, a ship that is
30% overloaded and is traveling 175 miles has a 30 x 175/250 = 21% chance of capsizing during the trip. If a
ship capsizes, then everyone and everything on it will be destroyed. If the group leader of a sailing group has
more than one galley in his command, then all of the galleys will capsize.

APPENDIX C: RESERVED WORDS [ Table of Contents ]

The command language has several words that are reserved for its own use and which may not be used in
names. Here is a complete list:

Adverbs:

Repeatedly, Immediately, Briefly, Definitely, Suicidally, Recklessly, Bravely,
Cautiously, Cravenly, Fully, Silently, Quietly
Verbs:

Absorb, Address, Assign, Attack, Await, Bless, Borrow, Build, Buy, Capture, Charge,
Collect, Come, Conjure, Construct, Cure, Curse, Discard, Dismiss, Execute, Explore,
Fly, Fortify, Free, Gather, Get, Give, Go, Halt, Heal, Hire, Interrogate, Join, Kill,
Lurk, Make, Mine, Name, Obtain, Offer, Password, Pay, Post, Pray, Probe, Promote,
Purchase, Query, Recharge, Recruit, Release, Report, Repay, Sail, Say, Scan, Search,
Secure, Sell, Stop, Study, Summon, Support, Take, Tax, Teach, Teleport, Tell, Train,
Travel, Unfortify, Unload, Unlurk, Unname, Wait, Work, ZZZ
Pronouns:

I, Me, You, Him, Her, It, Them
Prepositions:

By, For, From, To, Using, With
Items:

Armor, Catapult, Galley, Horse, Ram, Slave, Tower, Wagon, Weapon, Copper, Gem, Gold,
Iron, Silver, Stone, Wood
Summoned creatures:

Skeleton, Zombie, Harpy, Minotaur, Griffin, Chimera, Dragon, Demon
Ranks and titles:

Untitled, Worker, Soldier, Sailor, Mage, Friar, Sister, Baron, Baroness, Captain,
Ensign, Conjurer, Father, Mother, Count, Countess, Major, Mate, Sorcerer, Bishop, Duke,
Duchess, Colonel, Adept, Archbishop, Prince, Princess, King, Queen, General, Admiral,
Wizard, Primate, Emperor, Empress, Mister, Madam, Miss, Mistress, Sir, Dame, Squire,
Lady, Lord, Doctor, Engineer, Miner, Trader, Novice, Junior, Senior, Master, Ambassador
Others:

And, Have, Then, All, Every
An error will occur if you use one of these words when naming a character. For example, in the command
Name male soldier James Gold , the computer will assume that the name of the soldier is simply James and
that Gold is the beginning of the next command. And since a valid command cannot begin with the word
Gold , the computer will report an error. (It will also change the name James to something longer, because
names must have at least 8 characters.)

APPENDIX D: COMMAND SYNTAX [ Table of Contents ]

For those of you interested in the gory details, here is a BNF representation of the syntax of the command
language (it is not necessary to know any of this to play the game!):

Symbols:

| means logical "or"
() means that the enclosed item is optional.
{} means that the enclosed item may appear zero or more times.
Uncapitalized words are categories.
Capitalized words are terminals.

Syntax:

orders ::= {order}

order ::= (HAVE person) (REPEATEDLY) command {AND command}

command ::= (adverb) verb {(preposition) argument}

argument ::= entity {AND entity}

entity ::= person | quantifier item | (n) item
| (n) recruitable_rank | "message"
| (location_modifier) location_name
| pronoun

person ::= (rank) person_name

quantifier ::= ALL | EVERY | ALL HIS | ALL OF THE | etc.

n ::= any positive integer (1 and up)

pronoun ::= I | ME | YOU | HE | SHE | IT | THEM

adverb ::= BRIEFLY | CRAVENLY | DEFINITELY | etc.

verb ::= GO | RECRUIT | BUY | SUMMON | etc.

recruitable_rank ::= SOLDIER | SAILOR | WORKER

location_modifier ::= OUTSIDE | NEAR

rank ::= SOLDIER | CAPTAIN | MASTER | WIZARD | etc.

preposition ::= FOR | TO | FROM | BY | etc.

item ::= GOLD | CATAPULT | HORSE | (BATTERING) RAM | etc.

TABLE OF CONTENTS
Introduction
Game Timing "Have" and "And"
The Command Language The Adverb "Then"
Character Types And Names Groups And Group Leaders
Skills The Preposition "to"
Death Pronouns
Dead Leaders Numeric Quantities
Magic The Preposition "until"
Religion The Adverb "repeatedly"
Communications The Adverb "immediately"
Map Locations The Adverbs "quietly" and "silently"
Magical Items "If" statements
Magic-Free Zones
Player IDs Quitting the Game

Command Descriptions
**Absorb **Address **Ally **Assign **Attack **Await **Bless **Borrow **Build **Buy **Buy Passage
**Capture **Charge **Collect **Combatant **Come **Conjure **Construct **Create **Cure **Curse
**Discard **Dismiss **Enemy **Enslave **Execute **Explore **Fly **Fortify **Free **Gather **Get
**Give **Go **Halt **Heal **Hire **Interrogate **Join **Invest **Kill **Lurk **Make **Mine **Move
**Name **Neutral **Noncom **Obtain **Offer **Password **Pay **Post **Pray **Preach **Probe
**Promote **Purchase **Query **Recharge **Recruit **Repay **Report **Release **Sail **Say **Scan
**Search **Secure **Sell **Stop **Study **Summon **Support **Take **Tax **Teach **Teleport **Tell
**Train **Transfer **Travel **Unfortify **Unload **Unlurk **Unname **Wait **Work

Appendix A: Character Generation
Appendix B: Item Characteristics
Appendix C: Reserved Words
Appendix D: Command Syntax

End of rules for Spoils of Empire

Back to home page
This is a offline tool, your data stays locally and is not send to any server!
Feedback & Bug Reports
