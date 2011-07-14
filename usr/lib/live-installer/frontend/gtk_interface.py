#!/usr/bin/env python
import sys
sys.path.append('/usr/lib/live-installer')
from installer import InstallerEngine, fstab, fstab_entry, SystemUser #, HostMachine

try:
    import pygtk
    pygtk.require("2.0")
    import gtk
    import gtk.glade
    import gettext
    import os
    import commands
    import subprocess
    import sys
    sys.path.append('/usr/lib/live-installer')
    import pango
    import threading
    import xml.dom.minidom
    from xml.dom.minidom import parse
    import gobject
    import time
    # import webkit
    import GeoIP
    import urllib
    import webkit
    import string
except Exception, detail:
    print detail


import parted, commands

gettext.install("live-installer", "/usr/share/locale")
gtk.gdk.threads_init()

INDEX_PARTITION_PATH=0
INDEX_PARTITION_TYPE=1
INDEX_PARTITION_DESCRIPTION=2
INDEX_PARTITION_FORMAT_AS=3
INDEX_PARTITION_MOUNT_AS=4
INDEX_PARTITION_SIZE=5
INDEX_PARTITION_FREE_SPACE=6
INDEX_PARTITION_OBJECT=7

''' Handy. Makes message dialogs easy :D '''
class MessageDialog(object):

    def __init__(self, title, message, style):
        self.title = title
        self.message = message
        self.style = style

    ''' Show me on screen '''
    def show(self):

        dialog = gtk.MessageDialog(None, gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT, self.style, gtk.BUTTONS_OK, self.message)
        dialog.set_title(self.title)
        dialog.set_position(gtk.WIN_POS_CENTER)
        dialog.set_icon_from_file("/usr/share/icons/live-installer.png")
        dialog.run()
        dialog.destroy()

class WizardPage:

    def __init__(self, help_text):
        self.help_text = help_text        
		
class InstallerWindow:

    def __init__(self, fullscreen=False):
        self.resource_dir = '/usr/share/live-installer/'
        #self.glade = 'interface.glade'
        self.glade = os.path.join(self.resource_dir, 'interface.glade')
        self.wTree = gtk.glade.XML(self.glade, 'main_window')

        # should be set early
        self.done = False
        self.fail = False

        # here cometh the installer engine
        self.installer = InstallerEngine()
        # the distribution name
        DISTRIBUTION_NAME = self.installer.get_distribution_name()
        # load the window object
        self.window = self.wTree.get_widget("main_window")
        if "--debug" in sys.argv:
            self.window.set_title((_("%s Installer") % DISTRIBUTION_NAME) + " (debug)")
        else:
            self.window.set_title(_("%s Installer") % DISTRIBUTION_NAME)
        self.window.connect("destroy", self.quit_cb)

        # Wizard pages
        [self.PAGE_LANGUAGE, self.PAGE_PARTITIONS, self.PAGE_USER, self.PAGE_ADVANCED, self.PAGE_KEYBOARD, self.PAGE_OVERVIEW, self.PAGE_INSTALL, self.PAGE_TIMEZONE] = range(8)
        self.wizard_pages = range(8)
        self.wizard_pages[self.PAGE_LANGUAGE] = WizardPage(_("Choose your language"))
        self.wizard_pages[self.PAGE_TIMEZONE] = WizardPage(_("Choose your timezone"))
        self.wizard_pages[self.PAGE_KEYBOARD] = WizardPage(_("Choose your keyboard layout"))
        self.wizard_pages[self.PAGE_PARTITIONS] = WizardPage(_("Select where you want to install Linux Mint"))
        self.wizard_pages[self.PAGE_USER] = WizardPage(_("Please indicate your name and select a username, a password and a hostname"))
        self.wizard_pages[self.PAGE_ADVANCED] = WizardPage(_("Please review the following advanced options"))
        self.wizard_pages[self.PAGE_OVERVIEW] = WizardPage(_("Please review this summary and make sure everything is correct"))
        self.wizard_pages[self.PAGE_INSTALL] = WizardPage(_("Please wait while Linux Mint is being installed on your computer"))
        
        # set the button events (wizard_cb)
        self.wTree.get_widget("button_next").connect("clicked", self.wizard_cb, False)
        self.wTree.get_widget("button_back").connect("clicked", self.wizard_cb, True)
        self.wTree.get_widget("button_quit").connect("clicked", self.quit_cb)

        ren = gtk.CellRendererPixbuf()
        column = gtk.TreeViewColumn("Flags", ren)
        column.add_attribute(ren, "pixbuf", 2)
        self.wTree.get_widget("treeview_language_list").append_column(column)

        ren = gtk.CellRendererText()
        column = gtk.TreeViewColumn("Languages", ren)
        column.add_attribute(ren, "text", 0)
        self.wTree.get_widget("treeview_language_list").append_column(column)

        self.wTree.get_widget("treeview_language_list").connect("cursor-changed", self.cb_change_language)

        # build the language list
        self.build_lang_list()

        ren = gtk.CellRendererText()
        column = gtk.TreeViewColumn("Timezones", ren)
        column.add_attribute(ren, "text", 0)
        self.wTree.get_widget("treeview_timezones").append_column(column)

        self.wTree.get_widget("treeview_timezones").connect("cursor-changed", self.cb_change_timezone)

        self.build_timezones()

        # disk view
        self.wTree.get_widget("button_edit").connect("clicked", self.edit_partitions)
        self.wTree.get_widget("label_edit_partitions").set_label(_("Edit partitions"))
        self.wTree.get_widget("button_refresh").connect("clicked", self.refresh_partitions)
        self.wTree.get_widget("treeview_disks").connect("row_activated", self.assign_partition)
        self.wTree.get_widget("treeview_disks").connect( "button-release-event", self.partitions_popup_menu)

        # device
        ren = gtk.CellRendererText()
        column = gtk.TreeViewColumn(_("Device"), ren)
        column.add_attribute(ren, "markup", INDEX_PARTITION_PATH)
        self.wTree.get_widget("treeview_disks").append_column(column)
        # Type
        ren = gtk.CellRendererText()
        column = gtk.TreeViewColumn(_("Type"), ren)
        column.add_attribute(ren, "markup", INDEX_PARTITION_TYPE)
        self.wTree.get_widget("treeview_disks").append_column(column)
        # description
        ren = gtk.CellRendererText()
        column = gtk.TreeViewColumn(_("Operating system"), ren)
        column.add_attribute(ren, "markup", INDEX_PARTITION_DESCRIPTION)
        self.wTree.get_widget("treeview_disks").append_column(column)
        # format
        ren = gtk.CellRendererText()
        column = gtk.TreeViewColumn(_("Format as"), ren)
        column.add_attribute(ren, "markup", INDEX_PARTITION_FORMAT_AS)        
        self.wTree.get_widget("treeview_disks").append_column(column)      
        # mount point
        ren = gtk.CellRendererText()
        column = gtk.TreeViewColumn(_("Mount as"), ren)
        column.add_attribute(ren, "markup", INDEX_PARTITION_MOUNT_AS)
        self.wTree.get_widget("treeview_disks").append_column(column)
        # size
        ren = gtk.CellRendererText()
        column = gtk.TreeViewColumn(_("Size (MB)"), ren)
        column.add_attribute(ren, "markup", INDEX_PARTITION_SIZE)
        self.wTree.get_widget("treeview_disks").append_column(column)
        # Used space
        ren = gtk.CellRendererText()
        column = gtk.TreeViewColumn(_("Free space (MB)"), ren)
        column.add_attribute(ren, "markup", INDEX_PARTITION_FREE_SPACE)
        self.wTree.get_widget("treeview_disks").append_column(column)

        # about you
        self.wTree.get_widget("label_your_name").set_markup("<b>%s</b>" % _("Your full name"))
        self.wTree.get_widget("label_your_name_help").set_label(_("This will be shown in the About Me application"))
        self.wTree.get_widget("label_username").set_markup("<b>%s</b>" % _("Your username"))
        self.wTree.get_widget("label_username_help").set_label(_("This is the name you will use to login to your computer"))
        self.wTree.get_widget("label_choose_pass").set_markup("<b>%s</b>" % _("Your password"))
        self.wTree.get_widget("label_pass_help").set_label(_("Please enter your password twice to ensure it is correct"))
        self.wTree.get_widget("label_hostname").set_markup("<b>%s</b>" % _("Hostname"))
        self.wTree.get_widget("label_hostname_help").set_label(_("This hostname will be the computers name on the network"))

        self.wTree.get_widget("entry_your_name").connect("notify::text", self.update_account_fields)

        # try to set the hostname
        #machine = HostMachine()
        #model = machine.get_model()
        #hostname = ""
        #if(model is not None):
        #    model = model.replace(" ", "").lower()
        #    hostname = model + "-"
        #if(machine.is_laptop()):
        #    hostname += _("laptop")
        #else:
        #    hostname += _("desktop")
        #self.wTree.get_widget("entry_hostname").set_text(hostname)

        # events for detecting password mismatch..
        entry1 = self.wTree.get_widget("entry_userpass1")
        entry2 = self.wTree.get_widget("entry_userpass2")
        entry1.connect("changed", self.pass_mismatcher)
        entry2.connect("changed", self.pass_mismatcher)

        # grub
        self.wTree.get_widget("label_grub").set_markup("<b>%s</b>" % _("Bootloader"))
        self.wTree.get_widget("checkbutton_grub").set_label(_("Install GRUB"))
        self.wTree.get_widget("label_grub_help").set_label(_("GRUB is a bootloader used to load the Linux kernel"))

        # link the checkbutton to the combobox
        grub_check = self.wTree.get_widget("checkbutton_grub")
        grub_box = self.wTree.get_widget("combobox_grub")
        grub_check.connect("clicked", lambda x: grub_box.set_sensitive(x.get_active()))

        # Install Grub by default
        grub_check.set_active(True)
        grub_box.set_sensitive(True)

        # keyboard page
        self.wTree.get_widget("label_test_kb").set_label(_("Use this box to test your keyboard layout"))
        self.wTree.get_widget("label_kb_model").set_label(_("Model"))
        
        # kb models
        cell = gtk.CellRendererText()
        self.wTree.get_widget("combobox_kb_model").pack_start(cell, True)
        self.wTree.get_widget("combobox_kb_model").add_attribute(cell, 'text', 0)        
        self.wTree.get_widget("combobox_kb_model").connect("changed", self.cb_change_kb_model)

        # kb layouts
        ren = gtk.CellRendererText()
        column = gtk.TreeViewColumn(_("Layout"), ren)
        column.add_attribute(ren, "text", 0)
        self.wTree.get_widget("treeview_layouts").append_column(column)
        self.wTree.get_widget("treeview_layouts").connect("cursor-changed", self.cb_change_kb_layout)
        
        ren = gtk.CellRendererText()
        column = gtk.TreeViewColumn(_("Variant"), ren)
        column.add_attribute(ren, "text", 0)
        self.wTree.get_widget("treeview_variants").append_column(column)
        self.wTree.get_widget("treeview_variants").connect("cursor-changed", self.cb_change_kb_variant)
        
        self.build_kb_lists()

        # 'about to install' aka overview
        ren = gtk.CellRendererText()
        column = gtk.TreeViewColumn(_("Overview"), ren)
        column.add_attribute(ren, "markup", 0)
        self.wTree.get_widget("treeview_overview").append_column(column)
        # install page
        self.wTree.get_widget("label_install_progress").set_markup("<i>%s</i>" % _("Calculating file indexes..."))

        # build partition list
        self.should_pulse = False

        # make sure we're on the right page (no pun.)
        self.activate_page(0)

        # this is a hack atm to steal the menubar's background color
        self.wTree.get_widget("menubar").realize()
        style = self.wTree.get_widget("menubar").style.copy()
        self.wTree.get_widget("menubar").hide()
        # apply to the header       
        self.wTree.get_widget("help_label").realize()
        self.wTree.get_widget("help_label").modify_fg(gtk.STATE_NORMAL, style.fg[gtk.STATE_NORMAL])       
        if(fullscreen):
            # dedicated installer mode thingum
            self.window.maximize()
            self.window.fullscreen()        
        
        # ''' Launch the Slideshow '''
        # if ("_" in self.locale):
        #     locale_code = self.locale.split("_")[0]
        # else:
        #      locale_code = self.locale
        
        # slideshow_path = "/usr/share/live-installer-slideshow/slides/index.html"
        # if os.path.exists(slideshow_path):            
        #     browser = webkit.WebView()
        #     s = browser.get_settings()
        #     s.set_property('enable-file-access-from-file-uris', True)
        #     s.set_property('enable-default-context-menu', False)
        #     browser.open("file://" + slideshow_path  + "#?locale=" + locale_code)
        #     self.wTree.get_widget("vbox_install").add(browser)
        #     self.wTree.get_widget("vbox_install").show_all()            
                          
        self.window.show_all()

    def update_account_fields(self, entry, prop):
        text = entry.props.text.strip().lower()
        if " " in entry.props.text:
            elements = text.split()
            text = elements[0]
        self.wTree.get_widget("entry_username").set_text(text)

    def quit_cb(self, widget, data=None):
        ''' ask whether we should quit. because touchpads do happen '''
        gtk.main_quit()

    def assign_partition(self, widget, data=None, data2=None):
        ''' assign the partition ... '''
        model, iter = self.wTree.get_widget("treeview_disks").get_selection().get_selected()
        if iter is not None:
            row = model[iter]
            partition = row[INDEX_PARTITION_OBJECT]
            if not partition.real_type == parted.PARTITION_EXTENDED and not partition.partition.number == -1:                       
                dlg = PartitionDialog(row[INDEX_PARTITION_PATH], row[INDEX_PARTITION_MOUNT_AS], row[INDEX_PARTITION_FORMAT_AS], row[INDEX_PARTITION_DESCRIPTION])
                (mount_as, format_as) = dlg.show()
                # now set the model as shown..                
                row[INDEX_PARTITION_MOUNT_AS] = mount_as
                row[INDEX_PARTITION_FORMAT_AS] = format_as                
                model[iter] = row                
                
    def partitions_popup_menu( self, widget, event ):
        if event.button == 3:
            model, iter = self.wTree.get_widget("treeview_disks").get_selection().get_selected()
            if iter is not None:
                partition = model.get_value(iter, INDEX_PARTITION_OBJECT)
                if not partition.real_type == parted.PARTITION_EXTENDED and not partition.partition.number == -1:
                    menu = gtk.Menu()
                    menuItem = gtk.MenuItem(_("Edit"))
                    menuItem.connect( "activate", self.assign_partition, partition)
                    menu.append(menuItem)
                    menuItem = gtk.SeparatorMenuItem()
                    menu.append(menuItem)
                    menuItem = gtk.MenuItem(_("Assign to /"))
                    menuItem.connect( "activate", self.assignRoot, partition)
                    menu.append(menuItem)
                    menuItem = gtk.MenuItem(_("Assign to /home"))
                    menuItem.connect( "activate", self.assignHome, partition)
                    menu.append(menuItem)
                    menu.show_all()
                    menu.popup( None, None, None, event.button, event.time )

    def assignRoot(self, menu, partition):
        model = self.wTree.get_widget("treeview_disks").get_model()
        iter = model.get_iter_first()
        while iter is not None:
            iter_partition = model.get_value(iter, INDEX_PARTITION_OBJECT)
            if iter_partition == partition:
                model.set_value(iter, INDEX_PARTITION_MOUNT_AS, "/") # add / assignment
                model.set_value(iter, INDEX_PARTITION_FORMAT_AS, "ext4") # format                
            else:
                mountpoint = model.get_value(iter, INDEX_PARTITION_MOUNT_AS)
                if mountpoint == "/":
                    model.set_value(iter, INDEX_PARTITION_MOUNT_AS, "") # remove / assignment
                    model.set_value(iter, INDEX_PARTITION_FORMAT_AS, "") # don't format                   
            iter = model.iter_next(iter)

    def assignHome(self, menu, partition):
        model = self.wTree.get_widget("treeview_disks").get_model()
        iter = model.get_iter_first()
        while iter is not None:
            iter_partition = model.get_value(iter, INDEX_PARTITION_OBJECT)
            if iter_partition == partition:
                model.set_value(iter, INDEX_PARTITION_MOUNT_AS, "/home") # add /home assignment
                model.set_value(iter, INDEX_PARTITION_FORMAT_AS, "") # don't format                
            else:
                mountpoint = model.get_value(iter, INDEX_PARTITION_MOUNT_AS)
                if mountpoint == "/home":
                    model.set_value(iter, INDEX_PARTITION_MOUNT_AS, "") # remove /home assignment
                    model.set_value(iter, INDEX_PARTITION_FORMAT_AS, "") # don't format                    
            iter = model.iter_next(iter)

    def refresh_partitions(self, widget, data=None):
        ''' refresh the partitions ... '''
        thr = threading.Thread(name="live-installer-disk-search", group=None, target=self.build_partitions, args=(), kwargs={})
        thr.start()

    def edit_partitions(self, widget, data=None):
        ''' edit the partitions ... '''
        os.popen("gparted &")

    def build_lang_list(self):

        #Try to find out where we're located...
        cur_country_code = None
        try:
            whatismyip = 'http://debian.linuxmint.com/installer/show_my_ip.php'
            ip = urllib.urlopen(whatismyip).readlines()[0]
            gi = GeoIP.new(GeoIP.GEOIP_MEMORY_CACHE)
            cur_country_code = gi.country_code_by_addr(ip)
        except:
            pass #best effort, we get here if we're not connected to the Internet            

        #Plan B... find out what locale we're in (i.e. USA on the live session)
        cur_lang = os.environ['LANG']
        if("." in cur_lang):
            cur_lang = cur_lang.split(".")[0]

        model = gtk.ListStore(str,str,gtk.gdk.Pixbuf)
        model.set_sort_column_id(0, gtk.SORT_ASCENDING)

        #Load countries into memory
        countries = {}
        file = open(os.path.join(self.resource_dir, 'countries'), "r")
        for line in file:
            line = line.strip()
            split = line.split("=")
            if len(split) == 2:
                countries[split[0]] = split[1]
        file.close()

        #Load languages into memory
        languages = {}
        file = open(os.path.join(self.resource_dir, 'languages'), "r")
        for line in file:
            line = line.strip()
            split = line.split("=")
            if len(split) == 2:
                languages[split[0]] = split[1]
        file.close()

        path = os.path.join(self.resource_dir, 'locales')
        locales = open(path, "r")
        cur_index = -1 # find the locale :P
        set_index = None
        for line in locales:
            cur_index += 1
            if "UTF-8" in line:
                locale_code = line.replace("UTF-8", "")
                locale_code = locale_code.replace(".", "")
                locale_code = locale_code.strip()
                if "_" in locale_code:
                    split = locale_code.split("_")
                    if len(split) == 2:
                        language_code = split[0]
                        if language_code in languages:
                            language = languages[language_code]
                        else:
                            language = language_code

                        country_code = split[1].lower()
                        if country_code in countries:
                            country = countries[country_code]
                        else:
                            country = country_code

                        language_label = "%s (%s)" % (language, country)
                        #language_label = "%s - %s" % (country, language)

                        iter = model.append()
                        model.set_value(iter, 0, language_label)
                        model.set_value(iter, 1, locale_code)
                        flag_path = self.resource_dir + '/flags/16/' + country_code + '.png'
                        if os.path.exists(flag_path):
                            model.set_value(iter, 2, gtk.gdk.pixbuf_new_from_file(flag_path))
                        else:
                            flag_path = self.resource_dir + '/flags/16/generic.png'
                            model.set_value(iter, 2, gtk.gdk.pixbuf_new_from_file(flag_path))
                        # If it's matching our country code, that's our language right there.. 
                        if ((cur_country_code is not None) and (cur_country_code.lower() == country_code)):                            
                            if (set_index is None):
                                set_index = iter                                
                            else:
                                # If we find more than one language for a particular country, one of them being English, go for English by default.
                                if (language_code == "en"):
                                    set_index = iter                 
                                # Guesswork... handy for countries which have their own language (fr_FR, de_DE, es_ES.. etc. )
                                elif (country_code == language_code):
                                    set_index = iter
                                    
                        # as a plan B... use the locale (USA)
                        if((set_index is None) and (locale_code == cur_lang)):
                            set_index = iter
                            #print "Set via locale: " + cur_lang

        treeview = self.wTree.get_widget("treeview_language_list")
        treeview.set_model(model)
        if(set_index is not None):
            column = treeview.get_column(0)
            path = model.get_path(set_index)
            treeview.set_cursor(path, focus_column=column)
            treeview.scroll_to_cell(path, column=column)
        treeview.set_search_column(0)

    def build_timezones(self):
        model = gtk.ListStore(str, str)
        model.set_sort_column_id(0, gtk.SORT_ASCENDING)

        path = os.path.join(self.resource_dir, 'timezones')
        timezones = open(path, "r")
        cur_index = -1 # find the timezone :P
        set_index = None
        for line in timezones:
            cur_index += 1
            content = line.strip().split()
            if len(content) == 2:
                country_code = content[0]
                timezone = content[1]
                iter = model.append()
                model.set_value(iter, 0, timezone)
                model.set_value(iter, 1, country_code)

        treeview = self.wTree.get_widget("treeview_timezones")
        treeview.set_model(model)
        treeview.set_search_column(0)
  
    def build_partitions(self):
        gtk.gdk.threads_enter()
        self.window.set_sensitive(False)
        # "busy" cursor.
        cursor = gtk.gdk.Cursor(gtk.gdk.WATCH)
        self.window.window.set_cursor(cursor)
        from progress import ProgressDialog
        dialog = ProgressDialog()
        dialog.show(title=_("Installer"), label=_("Scanning for partitions"))
        gtk.gdk.threads_leave()
        from screen import Partition
        os.popen('mkdir -p /tmp/live-installer/tmpmount')
        
        try:
        
            disks = [] 
            
            inxi = subprocess.Popen("inxi -c0 -D", shell=True, stdout=subprocess.PIPE)        
            for line in inxi.stdout:
                line = line.rstrip("\r\n")
                if(line.startswith("Disks:")):
                    line = line.replace("Disks:", "")            
                sections = line.split(":")
                for section in sections:
                    section = section.strip()
                    if("/dev/" in section):                    
                        elements = section.split()
                        for element in elements:
                            if "/dev/" in element:
                                disks.append(element)                                
                                            
            grub_model = gtk.ListStore(str)
            partitions = []
            
            html_partitions = ""        
            model = gtk.ListStore(str,str,str,str,str,str,str, object, bool, str, str, bool)
            model2 = gtk.ListStore(str)
            
            for disk in disks:                 
                path =  disk # i.e. /dev/sda
                grub_model.append([path])
                device = parted.getDevice(path)
                disk = parted.Disk(device)
                partition = disk.getFirstPartition()
                last_added_partition = Partition(partition)
                partitions.append(last_added_partition)
                partition = partition.nextPartition()
                html_partitions = html_partitions + "<table width='100%'><tr>"
                while (partition is not None):
                    if last_added_partition.partition.number == -1 and partition.number == -1:
                        last_added_partition.add_partition(partition)
                    else:
                        last_added_partition = Partition(partition)
                        partitions.append(last_added_partition)
                
                        if "swap" in last_added_partition.type:
                            last_added_partition.type = _("swap")

                        if partition.number != -1 and "swap" not in last_added_partition.type and partition.type != parted.PARTITION_EXTENDED:
                            
                            grub_model.append([partition.path])

                            #Umount temp folder
                            if ('/tmp/live-installer/tmpmount' in commands.getoutput('mount')):
                                os.popen('umount /tmp/live-installer/tmpmount')

                            #Mount partition if not mounted
                            if (partition.path not in commands.getoutput('mount')):                                
                                os.system("mount %s /tmp/live-installer/tmpmount" % partition.path)

                            #Identify partition's description and used space
                            if (partition.path in commands.getoutput('mount')):
                                df_lines = commands.getoutput("df 2>/dev/null | grep %s" % partition.path).split('\n')
                                for df_line in df_lines:
                                    df_elements = df_line.split()
                                    if df_elements[0] == partition.path:
                                        last_added_partition.used_space = df_elements[4]  
                                        mount_point = df_elements[5]                              
                                        if "%" in last_added_partition.used_space:
                                            used_space_pct = int(last_added_partition.used_space.replace("%", "").strip())
                                            last_added_partition.free_space = int(float(last_added_partition.size) * (float(100) - float(used_space_pct)) / float(100))                                            
                                                                            
                                        if os.path.exists(os.path.join(mount_point, 'etc/lsb-release')):
                                            last_added_partition.description = commands.getoutput("cat " + os.path.join(mount_point, 'etc/lsb-release') + " | grep DISTRIB_DESCRIPTION").replace('DISTRIB_DESCRIPTION', '').replace('=', '').replace('"', '').strip()                                    
                                        if os.path.exists(os.path.join(mount_point, 'etc/issue')):
                                            last_added_partition.description = commands.getoutput("cat " + os.path.join(mount_point, 'etc/issue')).replace('\\n', '').replace('\l', '').strip()                                    
                                        if os.path.exists(os.path.join(mount_point, 'Windows/servicing/Version')):
                                            version = commands.getoutput("ls %s" % os.path.join(mount_point, 'Windows/servicing/Version'))                                    
                                            if version.startswith("6.1"):
                                                last_added_partition.description = "Windows 7"
                                            elif version.startswith("6.0"):
                                                last_added_partition.description = "Windows Vista"
                                            elif version.startswith("5.1") or version.startswith("5.2"):
                                                last_added_partition.description = "Windows XP"
                                            elif version.startswith("5.0"):
                                                last_added_partition.description = "Windows 2000"
                                            elif version.startswith("4.90"):
                                                last_added_partition.description = "Windows Me"
                                            elif version.startswith("4.1"):
                                                last_added_partition.description = "Windows 98"
                                            elif version.startswith("4.0.1381"):
                                                last_added_partition.description = "Windows NT"
                                            elif version.startswith("4.0.950"):
                                                last_added_partition.description = "Windows 95"
                                        elif os.path.exists(os.path.join(mount_point, 'Boot/BCD')):
                                            if os.system("grep -qs \"V.i.s.t.a\" " + os.path.join(mount_point, 'Boot/BCD')) == 0:
                                                last_added_partition.description = "Windows Vista bootloader"
                                            elif os.system("grep -qs \"W.i.n.d.o.w.s. .7\" " + os.path.join(mount_point, 'Boot/BCD')) == 0:
                                                last_added_partition.description = "Windows 7 bootloader"
                                            elif os.system("grep -qs \"W.i.n.d.o.w.s. .R.e.c.o.v.e.r.y. .E.n.v.i.r.o.n.m.e.n.t\" " + os.path.join(mount_point, 'Boot/BCD')) == 0:
                                                last_added_partition.description = "Windows recovery"
                                            elif os.system("grep -qs \"W.i.n.d.o.w.s. .S.e.r.v.e.r. .2.0.0.8\" " + os.path.join(mount_point, 'Boot/BCD')) == 0:
                                                last_added_partition.description = "Windows Server 2008 bootloader"
                                            else:
                                                last_added_partition.description = "Windows bootloader"
                                        elif os.path.exists(os.path.join(mount_point, 'Windows/System32')):
                                            last_added_partition.description = "Windows"
                                        break
                            else:
                                print "Failed to mount %s" % partition.path

                            
                            #Umount temp folder
                            if ('/tmp/live-installer/tmpmount' in commands.getoutput('mount')):
                                os.popen('umount /tmp/live-installer/tmpmount')
                                
                    if last_added_partition.size > 1.0:
                        if last_added_partition.real_type == parted.PARTITION_LOGICAL:
                            display_name = "  " + last_added_partition.name
                        else:
                            display_name = last_added_partition.name

                        iter = model.append([display_name, last_added_partition.type, last_added_partition.description, "", "", '%.0f' % round(last_added_partition.size, 0), last_added_partition.free_space, last_added_partition, False, last_added_partition.start, last_added_partition.end, False]);
                        if last_added_partition.partition.number == -1:                     
                            model.set_value(iter, INDEX_PARTITION_TYPE, "<span foreground='#a9a9a9'>%s</span>" % last_added_partition.type)                                    
                        elif last_added_partition.real_type == parted.PARTITION_EXTENDED:                    
                            model.set_value(iter, INDEX_PARTITION_TYPE, "<span foreground='#a9a9a9'>%s</span>" % _("Extended"))  
                        else:                                        
                            if last_added_partition.type == "ntfs":
                                color = "#42e5ac"
                            elif last_added_partition.type == "fat32":
                                color = "#18d918"
                            elif last_added_partition.type == "ext4":
                                color = "#4b6983"
                            elif last_added_partition.type == "ext3":
                                color = "#7590ae"
                            elif last_added_partition.type in ["linux-swap", "swap"]:
                                color = "#c1665a"
                            else:
                                color = "#a9a9a9"
                            model.set_value(iter, INDEX_PARTITION_TYPE, "<span foreground='%s'>%s</span>" % (color, last_added_partition.type))                                            
                            html_partition = "<td class='partition-cell' title='$title' style='border: 3px solid $color;' width='$space%'><div class='partition'>\n  <div style='width: $usage; background-color: #f8f8ba; height: 50px'></div>\n <div class='partition-text'>$path</div><div class='partition-os'>$OS</div>\n</div>\n</td>"        
                            deviceSize = float(device.getSize()) * float(0.9) # Hack.. reducing the real size to 90% of what it is, to make sure our partitions fit..
                            space = int((float(partition.getSize()) / deviceSize) * float(80))                            
                            subs = {}
                            if (space >= 10):
                                subs['path'] = display_name.replace("/dev/", "")                            
                                subs['OS'] = last_added_partition.description
                            elif (space >= 5):
                                subs['path'] = display_name.replace("/dev/", "")                            
                                subs['OS'] = ""                            
                            else:
                                #Not enough space, don't write the name
                                subs['path'] = ""                          
                                subs['OS'] = ""
                            subs['color'] = color                            
                            if (space == 0):
                                space = 1
                            subs['space'] = space
                            subs['title'] = display_name + "\n" + last_added_partition.description
                            if "%" in last_added_partition.used_space:               
                                subs['usage'] = last_added_partition.used_space.strip()
                            html_partition = string.Template(html_partition).safe_substitute(subs)                     
                            html_partitions = html_partitions + html_partition
                            
                    partition = partition.nextPartition()
                html_partitions = html_partitions + "</tr></table>"
            self.wTree.get_widget("combobox_grub").set_model(grub_model)
            self.wTree.get_widget("combobox_grub").set_active(0)
            gtk.gdk.threads_enter()
            
            
            import tempfile
            
            html_header = "<html><head><style>body {background-color:#d6d6d6;} \
            .partition{position:relative; width:100%; float: left; background: white;} \
            .partition-cell{ position:relative; margin: 2px 5px 2px 0; padding: 1px; float: left; background: white;} \
            .partition-text{ position:absolute; top:10; text-align: center; width=100px; left: 0; right: 0; margin: 0 auto; font-size:12px; } \
            .partition-os{ position:absolute; top:30; text-align: center; width=100px; left: 0; right: 0; margin: 0 auto; font-size:10px; font-style:italic;color:#555555;} </style></head><body>"
            html_footer = "</body></html>"
            html = html_header + html_partitions + html_footer
           
            # create temporary file
            f = tempfile.NamedTemporaryFile(delete=False)
            f.write(html)
            f.close()  
            
            browser = webkit.WebView()
            s = browser.get_settings()
            s.set_property('enable-file-access-from-file-uris', True)
            s.set_property('enable-default-context-menu', False)            
            browser.open(f.name)            
            #browser.load_html_string(html, "file://")     
            self.wTree.get_widget("scrolled_partitions").add(browser)
            self.wTree.get_widget("scrolled_partitions").show_all()    
                                                         
            
            gtk.gdk.threads_leave()
            
            gtk.gdk.threads_enter()
            self.wTree.get_widget("treeview_disks").set_model(model)
            gtk.gdk.threads_leave()
            dialog.hide()
            gtk.gdk.threads_enter()
            self.window.set_sensitive(True)
            self.window.window.set_cursor(None)
            gtk.gdk.threads_leave()
        except Exception, detail:
            print detail
                                      
                
        

    def build_kb_lists(self):
        ''' Do some xml kung-fu and load the keyboard stuffs '''

        # firstly we'll determine the layouts in use
        p = subprocess.Popen("setxkbmap -print",shell=True,stdout=subprocess.PIPE)
        for line in p.stdout:
            # strip it
            line = line.rstrip("\r\n")
            line = line.replace("{","")
            line = line.replace("}","")
            line = line.replace(";","")
            if("xkb_symbols" in line):
                # decipher the layout in use
                section = line.split("\"")[1] # split by the " mark
                self.keyboard_layout = section.split("+")[1]
            if("xkb_geometry" in line):
                first_bracket = line.index("(") +1
                substr = line[first_bracket:]
                last_bracket = substr.index(")")
                substr = substr[0:last_bracket]
                self.keyboard_geom = substr
        p.poll()

        xml_file = '/usr/share/X11/xkb/rules/xorg.xml'
        model_models = gtk.ListStore(str,str)
        model_models.set_sort_column_id(0, gtk.SORT_ASCENDING)
        model_layouts = gtk.ListStore(str,str)
        model_layouts.set_sort_column_id(0, gtk.SORT_ASCENDING)        
        dom = parse(xml_file)

        # if we find the users keyboard info we can set it in the list
        set_keyboard_model = None
        set_keyboard_layout = None
        set_keyboard_variant = None

        # grab the root element
        root = dom.getElementsByTagName('xkbConfigRegistry')[0]
        # build the list of models
        root_models = root.getElementsByTagName('modelList')[0]
        for element in root_models.getElementsByTagName('model'):
            conf = element.getElementsByTagName('configItem')[0]
            name = conf.getElementsByTagName('name')[0]
            desc = conf.getElementsByTagName('description')[0]
            #vendor = conf.getElementsByTagName('vendor')[0] # presently unused..
            iter_model = model_models.append([self.getText(desc.childNodes), self.getText(name.childNodes)])
            item = self.getText(name.childNodes)
            if(item == self.keyboard_geom):
                set_keyboard_model = iter_model
        root_layouts = root.getElementsByTagName('layoutList')[0]
        for element in root_layouts.getElementsByTagName('layout'):
            conf = element.getElementsByTagName('configItem')[0]
            name = conf.getElementsByTagName('name')[0]
            desc = conf.getElementsByTagName('description')[0]
            iter_layout = model_layouts.append([self.getText(desc.childNodes), self.getText(name.childNodes)])
            item = self.getText(name.childNodes)
            if(item == self.keyboard_layout):
                set_keyboard_layout = iter_layout
        # now set the model        
        self.wTree.get_widget("combobox_kb_model").set_model(model_models)
        self.wTree.get_widget("treeview_layouts").set_model(model_layouts)

        if(set_keyboard_layout is not None):
            # show it in the list
            treeview = self.wTree.get_widget("treeview_layouts")
            model = treeview.get_model()
            column = treeview.get_column(0)
            path = model.get_path(set_keyboard_layout)
            treeview.set_cursor(path, focus_column=column)
            treeview.scroll_to_cell(path, column=column)
        if(set_keyboard_model is not None):         
             # show it in the combo
            combo = self.wTree.get_widget("combobox_kb_model")
            model = combo.get_model()                    
            combo.set_active_iter(set_keyboard_model)            
            
    def build_kb_variant_lists(self):
        # firstly we'll determine the layouts in use
        p = subprocess.Popen("setxkbmap -print",shell=True,stdout=subprocess.PIPE)
        for line in p.stdout:
            # strip it
            line = line.rstrip("\r\n")
            line = line.replace("{","")
            line = line.replace("}","")
            line = line.replace(";","")
            if("xkb_symbols" in line):
                # decipher the layout in use
                section = line.split("\"")[1] # split by the " mark
                self.keyboard_layout = section.split("+")[1]
        p.poll()

        xml_file = '/usr/share/X11/xkb/rules/xorg.xml'      
        model_variants = gtk.ListStore(str,str)
        model_variants.set_sort_column_id(0, gtk.SORT_ASCENDING)        
        dom = parse(xml_file)
        
        # grab the root element
        root = dom.getElementsByTagName('xkbConfigRegistry')[0]
        # build the list of variants       
        root_layouts = root.getElementsByTagName('layoutList')[0]
        for layout in root_layouts.getElementsByTagName('layout'):
            conf = layout.getElementsByTagName('configItem')[0]
            layout_name = self.getText(conf.getElementsByTagName('name')[0].childNodes)            
            layout_description = self.getText(conf.getElementsByTagName('description')[0].childNodes)            
            if (layout_name == self.keyboard_layout):
                iter_variant = model_variants.append([layout_description, None])  
                variants_list = layout.getElementsByTagName('variantList')
                if len(variants_list) > 0:
                    root_variants = layout.getElementsByTagName('variantList')[0]   
                    for variant in root_variants.getElementsByTagName('variant'):                    
                        variant_conf = variant.getElementsByTagName('configItem')[0]
                        variant_name = self.getText(variant_conf.getElementsByTagName('name')[0].childNodes)
                        variant_description = "%s - %s" % (layout_description, self.getText(variant_conf.getElementsByTagName('description')[0].childNodes))
                        iter_variant = model_variants.append([variant_description, variant_name])                                                    
                break
                                                                                
        # now set the model        
        self.wTree.get_widget("treeview_variants").set_model(model_variants)
        
        # select the first item (standard variant layout)
        treeview = self.wTree.get_widget("treeview_variants")
        model = treeview.get_model()
        column = treeview.get_column(0)
        path = model.get_path(model.get_iter_first())
        treeview.set_cursor(path, focus_column=column)

    def getText(self, nodelist):
        rc = []
        for node in nodelist:
            if node.nodeType == node.TEXT_NODE:
                rc.append(node.data)
        return ''.join(rc)

    def cb_change_language(self, treeview, data=None):
        ''' Called whenever someone updates the language '''
        model = treeview.get_model()
        active = treeview.get_selection().get_selected_rows()
        if(len(active) < 1):
            return
        active = active[1][0]
        if(active is None):
            return
        row = model[active]
        self.locale = row[1]

    def cb_change_timezone(self, treeview, data=None):
        ''' Called whenever someone updates the timezone '''
        model = treeview.get_model()
        active = treeview.get_selection().get_selected_rows()
        if(len(active) < 1):
            return
        active = active[1][0]
        if(active is None):
            return
        row = model[active]
        self.timezone = row[0]
        self.timezone_code = row[1]
           
    def cb_change_kb_model(self, combobox, data=None):
        ''' Called whenever someone updates the keyboard model '''
        model = combobox.get_model()
        active = combobox.get_active()
        if(active > -1):
            row = model[active]
            os.system("setxkbmap -model %s" % row[1])
            self.keyboard_model = row[1]
            self.keyboard_model_desc = row[0]

    def cb_change_kb_layout(self, treeview, data=None):
        ''' Called whenever someone updates the keyboard layout '''
        model = treeview.get_model()
        active = treeview.get_selection().get_selected_rows()
        if(len(active) < 1):
            return
        active = active[1][0]
        if(active is None):
            return
        row = model[active]
        os.system("setxkbmap -layout %s" % row[1])
        self.keyboard_layout = row[1]
        self.keyboard_layout_desc = row[0]
        self.build_kb_variant_lists()
        
    def cb_change_kb_variant(self, treeview, data=None):
        ''' Called whenever someone updates the keyboard layout '''
        model = treeview.get_model()
        active = treeview.get_selection().get_selected_rows()
        if(len(active) < 1):
            return
        active = active[1][0]
        if(active is None):
            return
        row = model[active]
        if (row[1] is None):
            os.system("setxkbmap -layout %s" % self.keyboard_layout)
        else:
            os.system("setxkbmap -variant %s" % row[1])
        self.keyboard_variant = row[1]
        self.keyboard_variant_desc = row[0]

    def pass_mismatcher(self, widget):
        ''' Someone typed into the entry '''
        w = self.wTree.get_widget("entry_userpass1")
        w2 = self.wTree.get_widget("entry_userpass2")
        txt1 = w.get_text()
        txt2 = w2.get_text()
        if(txt1 == "" and txt2 == ""):
            self.wTree.get_widget("image_mismatch").hide()
            self.wTree.get_widget("label_mismatch").hide()
        else:
            self.wTree.get_widget("image_mismatch").show()
            self.wTree.get_widget("label_mismatch").show()
        if(txt1 != txt2):
            img = self.wTree.get_widget("image_mismatch")
            img.set_from_stock(gtk.STOCK_NO, gtk.ICON_SIZE_BUTTON)
            label = self.wTree.get_widget("label_mismatch")
            label.set_label(_("Passwords do not match"))
        else:
            img = self.wTree.get_widget("image_mismatch")
            img.set_from_stock(gtk.STOCK_OK, gtk.ICON_SIZE_BUTTON)
            label = self.wTree.get_widget("label_mismatch")
            label.set_label(_("Passwords match"))

    def activate_page(self, index):
        self.wTree.get_widget("help_label").set_markup("<big><b>%s</b></big>" % self.wizard_pages[index].help_text)
        self.wTree.get_widget("notebook1").set_current_page(index)


    def wizard_cb(self, widget, goback, data=None):
        ''' wizard buttons '''
        sel = self.wTree.get_widget("notebook1").get_current_page()
        self.wTree.get_widget("button_next").set_label(_("Forward"))
        
        # check each page for errors
        if(not goback):
            if(sel == self.PAGE_LANGUAGE):
                if ("_" in self.locale):
                    country_code = self.locale.split("_")[1]
                else:
                    country_code = self.locale
                treeview = self.wTree.get_widget("treeview_timezones")
                model = treeview.get_model()
                iter = model.get_iter_first()
                while iter is not None:
                    iter_country_code = model.get_value(iter, 1)
                    if iter_country_code == country_code:
                        column = treeview.get_column(0)
                        path = model.get_path(iter)
                        treeview.set_cursor(path, focus_column=column)
                        treeview.scroll_to_cell(path, column=column)
                        break
                    iter = model.iter_next(iter)
                self.activate_page(self.PAGE_TIMEZONE)
            elif (sel == self.PAGE_TIMEZONE):
                if ("_" in self.locale):
                    country_code = self.locale.split("_")[1]
                else:
                    country_code = self.locale
                treeview = self.wTree.get_widget("treeview_layouts")
                model = treeview.get_model()
                iter = model.get_iter_first()                
                while iter is not None:
                    iter_country_code = model.get_value(iter, 1)
                    if iter_country_code.lower() == country_code.lower():
                        column = treeview.get_column(0)
                        path = model.get_path(iter)
                        treeview.set_cursor(path, focus_column=column)
                        treeview.scroll_to_cell(path, column=column)
                        break
                    iter = model.iter_next(iter)
                self.activate_page(self.PAGE_KEYBOARD)
            elif(sel == self.PAGE_KEYBOARD):
                self.activate_page(self.PAGE_PARTITIONS)
                thr = threading.Thread(name="live-installer-disk-search", group=None, target=self.build_partitions, args=(), kwargs={})
                thr.start()                
            elif(sel == self.PAGE_PARTITIONS):                
                model = self.wTree.get_widget("treeview_disks").get_model()
                error = True
                errorMessage = _("Please select a root (/) partition before proceeding")
                for row in model:
                    mountpoint = row[3]
                    if(mountpoint == "/"):
                        error = False
                        format = row[2]
                        if format is None or format == "":
                            error = True
                            errorMessage = _("Please indicate a filesystem to format the root (/) partition before proceeding")                        
                if(error):
                    MessageDialog(_("Installation Tool"), errorMessage, gtk.MESSAGE_ERROR).show()
                else:
                    self.activate_page(self.PAGE_USER)
            elif(sel == self.PAGE_USER):
                errorFound = False
                errorMessage = ""
                
                username = self.wTree.get_widget("entry_username").get_text()
                password1 = self.wTree.get_widget("entry_userpass1").get_text()
                password2 = self.wTree.get_widget("entry_userpass2").get_text()
                hostname = self.wTree.get_widget("entry_hostname").get_text()
                
                if(username == ""):
                    errorFound = True
                    errorMessage = _("Please provide a username")
                elif(password1 == ""):
                    errorFound = True
                    errorMessage = _("Please provide a password for your user account")
                elif(password1 != password2):
                    errorFound = True
                    errorMessage = _("Your passwords do not match")
                elif(hostname == ""):
                    errorFound = True
                    errorMessage = _("Please provide a hostname")

                for char in username:
                    if(char.isupper()):
                        errorFound = True
                        errorMessage = _("Your username must be lower case")
                        break
                    elif(char.isspace()):
                        errorFound = True
                        errorMessage = _("Your username may not contain whitespace")
                
                for char in hostname:
                    if(char.isupper()):
                        errorFound = True
                        errorMessage = _("Your hostname must be lower case")
                        break
                    elif(char.isspace()):
                        errorFound = True
                        errorMessage = _("Your hostname may not contain whitespace")
                    
                if (errorFound):
                    MessageDialog(_("Installation Tool"), errorMessage, gtk.MESSAGE_WARNING).show()
                else:
                     self.activate_page(self.PAGE_ADVANCED)
            elif(sel == self.PAGE_ADVANCED):
                self.activate_page(self.PAGE_OVERVIEW)
                self.show_overview()
                self.wTree.get_widget("treeview_overview").expand_all()
                self.wTree.get_widget("button_next").set_label(_("Install"))
            elif(sel == self.PAGE_OVERVIEW):
                self.activate_page(self.PAGE_INSTALL)
                # do install
                self.wTree.get_widget("button_next").hide()
                self.wTree.get_widget("button_back").hide()
                thr = threading.Thread(name="live-install", group=None, args=(), kwargs={}, target=self.do_install)
                thr.start()
            self.wTree.get_widget("button_back").set_sensitive(True)
        else:
            if(sel == self.PAGE_OVERVIEW):
                self.activate_page(self.PAGE_ADVANCED)
            elif(sel == self.PAGE_ADVANCED):
                self.activate_page(self.PAGE_USER)
            elif(sel == self.PAGE_USER):
                self.activate_page(self.PAGE_PARTITIONS)                
            elif(sel == self.PAGE_PARTITIONS):
                self.activate_page(self.PAGE_KEYBOARD)
            elif(sel == self.PAGE_KEYBOARD):
                self.activate_page(self.PAGE_TIMEZONE)
            elif(sel == self.PAGE_TIMEZONE):
                self.activate_page(self.PAGE_LANGUAGE)
                self.wTree.get_widget("button_back").set_sensitive(False)

    def show_overview(self):
        ''' build the summary page '''
        model = gtk.TreeStore(str)
        
        print " ## OVERVIEW "

        top = model.append(None)
        model.set(top, 0, _("Localization"))
        iter = model.append(top)
        model.set(iter, 0, _("Language: ") + "<b>%s</b>" % self.locale)
        print " Language: %s " % self.locale
        iter = model.append(top)
        model.set(iter, 0, _("Timezone: ") + "<b>%s</b>" % self.timezone)
        print " Timezone: %s " % self.timezone
        iter = model.append(top)
        model.set(iter, 0, _("Keyboard layout: ") + "<b>%s</b>" % self.keyboard_layout_desc)
        print " Keyboard layout: %s " % self.keyboard_layout_desc
        iter = model.append(top)
        model.set(iter, 0, _("Keyboard model: ") + "<b>%s</b>" % self.keyboard_model_desc)
        print " Keyboard model: %s " % self.keyboard_model_desc

        top = model.append(None)
        model.set(top, 0, _("User settings"))
        username = self.wTree.get_widget("entry_username").get_text()
        realname = self.wTree.get_widget("entry_your_name").get_text()
        iter = model.append(top)
        model.set(iter, 0, _("Real name: ") + "<b>%s</b>" % realname)
        print " Real name: %s " % realname
        iter = model.append(top)
        model.set(iter, 0, _("Username: ") + "<b>%s</b>" % username)
        print " Username: %s " % username

        top = model.append(None)
        model.set(top, 0, _("System settings"))
        iter = model.append(top)
        model.set(iter, 0, _("Hostname: ") + "<b>%s</b>" % self.wTree.get_widget("entry_hostname").get_text())
        print " Hostname: %s " % self.wTree.get_widget("entry_hostname").get_text()

        install_grub = self.wTree.get_widget("checkbutton_grub").get_active()
        grub_box = self.wTree.get_widget("combobox_grub")
        grub_active = grub_box.get_active()
        grub_model = grub_box.get_model()
        iter = model.append(top)
        if(install_grub):
            model.set(iter, 0, _("Install bootloader in %s") % ("<b>%s</b>" % grub_model[grub_active][0]))
            print " Install bootloader in %s" % grub_model[grub_active][0]
        else:
            model.set(iter, 0, _("Do not install bootloader"))
            print " Do not install bootloader"

        top = model.append(None)
        model.set(top, 0, _("Filesystem operations"))
        disks = self.wTree.get_widget("treeview_disks").get_model()
        for item in disks:
            if(item[2] is not None and item[2] is not ""):
                # format it
                iter = model.append(top)
                model.set(iter, 0, "<b>%s</b>" % (_("Format %s (%s) as %s") % (item[0], item[4], item[2])))
                print " Format %s (%s) as %s" % (item[10].name, item[4], item[2])
        for item in disks:
            if(item[3] is not None and item[3] is not ""):
                # mount point
                iter = model.append(top)
                model.set(iter, 0, "<b>%s</b>" % (_("Mount %s as %s") % (item[0], item[3])))
                print " Mount %s as %s" % (item[10].name, item[3])       

        self.wTree.get_widget("treeview_overview").set_model(model)

    def do_install(self):
        
        try:        
            print " ## INSTALLATION "
            ''' Actually perform the installation .. '''
            inst = self.installer
            # Create fstab
            files = fstab()
            model = self.wTree.get_widget("treeview_disks").get_model()            
            for row in model:
                if((row[2] is not None and row[2] != "") or (row[3] is not None and row[3] != "")): # format or mountpoint specified.
                    filesystem = row[10].type
                    format = row[2]
                    mountpoint = row[3]
                    device = row[10].name
                    files.add_mount(device=device, mountpoint=mountpoint, filesystem=filesystem, format=format)                
            inst.fstab = files # need to add set_fstab() to InstallerEngine

            if "--debug" in sys.argv:
                print " ## DEBUG MODE - INSTALLATION PROCESS NOT LAUNCHED"            
                sys.exit(0)

            # set up the system user
            username = self.wTree.get_widget("entry_username").get_text()
            password = self.wTree.get_widget("entry_userpass1").get_text()
            realname = self.wTree.get_widget("entry_your_name").get_text()
            hostname = self.wTree.get_widget("entry_hostname").get_text()
            user = SystemUser(username=username, password=password, realname=realname)
            inst.set_main_user(user)
            inst.set_hostname(hostname)

            # set language
            inst.set_locale(self.locale)

            # set timezone
            inst.set_timezone(self.timezone, self.timezone_code)

            # set keyboard
            inst.set_keyboard_options(layout=self.keyboard_layout, model=self.keyboard_model)

            # grub?
            do_grub = self.wTree.get_widget("checkbutton_grub").get_active()
            if(do_grub):
                grub_box = self.wTree.get_widget("combobox_grub")
                grub_location = grub_box.get_model()[grub_box.get_active()][0]
                inst.set_install_bootloader(device=grub_location)
            inst.set_progress_hook(self.update_progress)
            inst.set_error_hook(self.error_message)

            # do we dare? ..
            self.critical_error_happened = False
            
            try:
                inst.install()
            except Exception, detail1:
                print detail1
                try:
                    gtk.gdk.threads_enter()
                    MessageDialog(_("Installation error"), str(detail), gtk.MESSAGE_ERROR).show()
                    gtk.gdk.threads_leave()
                except Exception, detail2:
                    print detail2

            # show a message dialog thingum
            while(not self.done):
                time.sleep(0.1)
            
            if self.critical_error_happened:
                gtk.gdk.threads_enter()
                MessageDialog(_("Installation error"), self.critical_error_message, gtk.MESSAGE_ERROR).show()
                gtk.gdk.threads_leave()                
            else:
                gtk.gdk.threads_enter()
                MessageDialog(_("Installation finished"), _("Installation is now complete. Please restart your computer to use the new system"), gtk.MESSAGE_INFO).show()
                gtk.gdk.threads_leave()
                
            print " ## INSTALLATION COMPLETE "
            
        except Exception, detail:
            print "!!!! General exception"
            print detail
            
        # safe??
        gtk.main_quit()
        # you are now..
        sys.exit(0)

    def error_message(self, message=""):
        self.critical_error_happened = True
        self.critical_error_message = message

    def update_progress(self, fail=False, done=False, pulse=False, total=0,current=0,message=""):
        
        #print "%d/%d: %s" % (current, total, message)
        
        # TODO: ADD FAIL CHECKS..
        if(pulse):
            gtk.gdk.threads_enter()
            self.wTree.get_widget("label_install_progress").set_label(message)
            gtk.gdk.threads_leave()
            self.do_progress_pulse(message)
            return
        if(done):
            # cool, finished :D
            self.should_pulse = False
            self.done = done
            gtk.gdk.threads_enter()
            self.wTree.get_widget("progressbar").set_fraction(1)
            self.wTree.get_widget("label_install_progress").set_label(message)
            gtk.gdk.threads_leave()
            return
        self.should_pulse = False
        _total = float(total)
        _current = float(current)
        pct = float(_current/_total)
        szPct = int(pct)
        # thread block
        gtk.gdk.threads_enter()
        self.wTree.get_widget("progressbar").set_fraction(pct)
        self.wTree.get_widget("label_install_progress").set_label(message)
        gtk.gdk.threads_leave()

        # end thread block

    def do_progress_pulse(self, message):
        def pbar_pulse():
            if(not self.should_pulse):
                return False
            gtk.gdk.threads_enter()
            self.wTree.get_widget("progressbar").pulse()
            gtk.gdk.threads_leave()
            return self.should_pulse
        if(not self.should_pulse):
            self.should_pulse = True
            gobject.timeout_add(100, pbar_pulse)
        else:
            # asssume we're "pulsing" already
            self.should_pulse = True
            pbar_pulse()

class PartitionDialog:

    def __init__(self, path, mount_as, format_as, type):
        self.resource_dir = '/usr/share/live-installer/'
        self.glade = os.path.join(self.resource_dir, 'interface.glade')
        self.dTree = gtk.glade.XML(self.glade, 'dialog')
        self.window = self.dTree.get_widget("dialog")
        self.window.set_title(_("Edit partition"))
               
        ''' Build supported filesystems list '''
        model = gtk.ListStore(str)        
        model.append([""])
        if type == _("swap"):        
            model.append(["swap"])
        else:
            try:
                for item in os.listdir("/sbin"):
                    if(item.startswith("mkfs.")):
                        fstype = item.split(".")[1]
                        model.append([fstype])
            except Exception, detail:
                print detail
                print _("Could not build supported filesystems list!")
        self.dTree.get_widget("combobox_use_as").set_model(model)
        
        if type == _("swap"):
            mounts = ["", "swap"]
        else:
            mounts = ["", "/", "/boot", "/tmp", "/home", "/srv"]
        model = gtk.ListStore(str)
        for mount in mounts:
            model.append([mount])
        self.dTree.get_widget("comboboxentry_mount_point").set_model(model)  
                
        # i18n
        self.dTree.get_widget("label_partition").set_markup("<b>%s</b>" % _("Device:"))
        self.dTree.get_widget("label_partition_value").set_label(path)        
        
        self.dTree.get_widget("label_use_as").set_markup(_("Format as:"))        
        cur = -1
        model = self.dTree.get_widget("combobox_use_as").get_model()
        for item in model:
            cur += 1
            if(item[0] == format_as):
                self.dTree.get_widget("combobox_use_as").set_active(cur)
                break
                
        self.dTree.get_widget("label_mount_point").set_markup(_("Mount as:"))
        self.dTree.get_widget("comboboxentry_mount_point").child.set_text(mount_as)         

    def show(self):
        self.window.run()
        self.window.hide()        
        w = self.dTree.get_widget("comboboxentry_mount_point")
        w.child.get_text().replace(" ","")
        mount_as = w.child.get_text()
        w = self.dTree.get_widget("combobox_use_as")
        # find filesystem ..
        active = w.get_active()
        model = w.get_model()[active]
        format_as = model[0]
        return (mount_as, format_as)
