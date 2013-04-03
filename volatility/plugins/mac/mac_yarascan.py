# Volatility
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or (at
# your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details. 
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA 

import volatility.plugins.malware.malfind as malfind
import volatility.plugins.mac.pstasks as pstasks
import volatility.plugins.mac.common as common
import volatility.utils as utils 
import volatility.debug as debug

try:
    import yara
    has_yara = True
except ImportError:
    has_yara = False

class MapYaraScanner(malfind.BaseYaraScanner):
    """A scanner over all memory regions of a process."""

    def __init__(self, task = None, **kwargs):
        """Scan the process address space through the VMAs.

        Args:
          task: The task_struct object for this task.
        """
        self.task = task
        malfind.BaseYaraScanner.__init__(self, address_space = task.get_process_address_space(), **kwargs)

    def scan(self, offset = 0, maxlen = None):
        for map in self.task.get_proc_maps():
            for match in malfind.BaseYaraScanner.scan(self, map.links.start, map.links.end - map.links.start):
                yield match

class mac_yarascan(malfind.YaraScan):
    """A shell in the mac memory image"""

    @staticmethod
    def is_valid_profile(profile):
        return profile.metadata.get('os', 'Unknown').lower() == 'mac'

    def calculate(self):
    
        ## we need this module imported
        if not has_yara:
            debug.error("Please install Yara from code.google.com/p/yara-project")
            
        ## leveraged from the windows yarascan plugin
        rules = self._compile_rules()
            
        ## set the linux plugin address spaces 
        common.set_plugin_members(self)
    
        ## FIXME: this may not handle all address spaces properly, especially
        ## the 32bit ones without a split space for user/kernel 

        if self._config.KERNEL:
            ## http://fxr.watson.org/fxr/source/osfmk/mach/i386/vm_param.h?v=xnu-2050.18.24
            if self.addr_space.profile.metadata.get('memory_model', '32bit') == "32bit":
                kernel_start = 0xc0000000
            else:
                kernel_start = 0xffffff8000000000

            scanner = malfind.DiscontigYaraScanner(rules = rules, 
                                                   address_space = self.addr_space) 
      
            for hit, address in scanner.scan(start_offset = kernel_start):
                yield (None, address, hit, 
                        scanner.address_space.zread(address, 64))
        else:
            # Scan each process memory block 
            for task in pstasks.mac_tasks(self._config).calculate():
                scanner = MapYaraScanner(task = task, rules = rules)
                for hit, address in scanner.scan():
                    yield (task, address, hit, 
                            scanner.address_space.zread(address, 64))
    
    def render_text(self, outfd, data):
        for task, address, hit, buf in data:
            if task:
                outfd.write("Task: {0} pid {1} rule {2} addr {3:#x}\n".format(
                    task.p_comm, task.p_pid, hit.rule, address))
            else:
                outfd.write("[kernel] rule {0} addr {1:#x}\n".format(hit.rule, address))
            
            outfd.write("".join(["{0:#018x}  {1:<48}  {2}\n".format(
                address + o, h, ''.join(c)) for o, h, c in utils.Hexdump(buf)]))