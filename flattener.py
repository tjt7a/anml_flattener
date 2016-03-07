#!/usr/bin/python

'''

	This is the ANML flattener. It accepts a hierarchical ANML file using 
	macros, and returns a flattened version using only elements.
		
	*So far only support STEs, Counters, and Inverters

	usage: flattener.py <input anml filename> <output anml filename>

	Author: Tom Tracy II (tjt7a@virginia.edu)
	v1.5
	
'''
import sys
import xml.etree.ElementTree as ET
import copy
import os.path
VERBOSITY = True

reference_addresses = {}

delimiter = "___"

# Flatten the macro
def flatten(root, macro_subtree, macro, parent_id, connection_dictionary):

	macro_id, macro_use, activations, substitutions = grab_macro_details(macro)

	# The new id is (path-to-macro)--(macro id)
	new_id = parent_id + delimiter + macro_id

	try:
		if VERBOSITY:
			print "Parsing: ", macro_use
		
		macro_subtree = ET.parse(macro_use).getroot()

	except IOError:

		print "Failed to open Macro: ", macro_use
		exit()

	header = macro_subtree.find('header')
	inner_inter = header.find('interface-declarations')
	inner_params = header.find('parameter-declarations')

	inner_interface_declarations = None
	inner_parameters = None

	if inner_inter is not None:
		inner_interface_declarations = grab_inner_declarations(inner_inter)
		
	if inner_params is not None:
		inner_parameters = grab_inner_parameters(inner_params)

	# Strip out the header; we're done here
	macro_subtree.remove(header)

	if inner_parameters is not None:
		if VERBOSITY:
			print "Inner Parameters: ", inner_parameters

		# If default value not over-ridden, add to substitutions
		for item in inner_parameters:
			if item not in substitutions:
				substitutions[item] = inner_parameters[item]

	if inner_interface_declarations is not None:
		if VERBOSITY:
			print "Inner Interfaces: ", inner_interface_declarations

	body = macro_subtree.find('body')
	port_defs = body.find('port-definitions')

	# Grab the port definitions
	ports_in, ports_out = grab_port_definitions(port_defs, new_id)

	# Strip out the port-defs; we're done here
	body.remove(port_defs)

	# Merge dictionaries
	connection_dictionary = dict(connection_dictionary.items() + ports_in.items())

	replace_substitutions(body, substitutions)

	# Activation tags for different elements
	activation_dictionary = {
		'state-transition-element':'activate-on-match',
		'counter':'activate-on-target',
		'inverter':'activate-on-high'}

	# For elements in the body
	for child in body:
		if child.tag == 'macro-reference':
				
			root, connection_dictionary = flatten(root, macro_subtree, child, new_id, connection_dictionary)

		elif child.tag in ['state-transition-element', 'counter', 'inverter']:

			# Update the id of the element
			temp_id = new_id + delimiter + child.attrib['id']
			child.set('id', temp_id)

			if temp_id in ports_out:

				for out_connection in ports_out[temp_id]:

					if VERBOSITY:
						print "ports out"
						print ports_out[temp_id]
						print "activations"
						print activations

					if len(activations.keys()) > 0:

						# We're inside the macro now, but our macro is linking out, so outside the macro (i think)
						for activation in activations[out_connection.split(delimiter)[-1]]:
							temp_element = ET.Element(activation_dictionary[child.tag])
							link_to = ''

							if activation[1] is not None:
								if activation[1] is not 'cnt':
									link_to = parent_id + delimiter + activation[0] + delimiter + activation[1]
								else:
									link_to = parent_id + delimiter + activation[0] + ":" + activation[1]

								temp_element.set('element', link_to)

							else:
								link_to = parent_id + delimiter + activation[0]
								temp_element.set('element', link_to)

							child.append(temp_element)

					root.append(child)
			else:

				for link in child.findall('activate-on-match'):

					new_value = new_id + delimiter + link.attrib['element']

					link.set('element', new_value)

				root.append(child)


		else:

			print "Oh shit; we found something we shouldnt have"
			print child.tag
			exit()

	else:
		if VERBOSITY:
			print "We have no macros!"
			print "There are no macro-references in ", parent_id


	return root, connection_dictionary

def grab_activations(activate_out):

	activations = {} # Empty dictionary of activations

	for a_f_m in activate_out.findall('activate-from-macro'):

		source = a_f_m.attrib['source']
		element = a_f_m.attrib['element'].split(':')
		element_id = element[0]

		if len(element) == 2:
			element_port = element[1]
		else:
			element_port = None

		destination = (element_id, element_port)			

		if source not in activations:
			activations[source] = [destination, ]
		else:
			activations[source].append(destination)

	return activations	

def grab_substitutions(substitute):
	substitutions = {} # Empty dictionary of substitutions

	for replace in substitute.findall('replace'):
		parameter_name = replace.attrib['parameter-name']
		replace_with = replace.attrib['replace-with']

		if replace_with:
			substitutions[parameter_name] = replace_with

	return substitutions

def grab_inner_parameters(parameter_declarations):
	inner_parameters = {}

	for child in parameter_declarations:
		inner_parameters[child.attrib['parameter-name']] = child.attrib['default-value']

	return inner_parameters

def grab_inner_declarations(inner_interface):
	inner_interface_declarations = {}

	for child in inner_interface:
		inner_interface_declarations[child.attrib['id']] = child.attrib['type']

	return inner_interface_declarations

def grab_port_definitions(port_defs, new_id):
	ports_in = {}
	ports_out = {}

	# Iterate through all ports in port definitions
	for child in port_defs:

		# If a port-in
		if child.tag == 'port-in':

			for element in child:

				activate_from_name = new_id+delimiter+child.attrib['id'] # Macro_id + external port name
				new_ste_name = new_id+delimiter+element.attrib['element'] # Macro_id + STE name

				# Another hack to disable translation for counter
				if ':cnt' not in new_ste_name:
					new_ste_name = new_ste_name.replace(':', delimiter)

				#if element.attrib['element'] in ports_in:
				#	ports_in[element.attrib['element']].append(child.attrib['id'])
				if activate_from_name in ports_in:
					ports_in[activate_from_name].append(new_ste_name)

				else:
					ports_in[activate_from_name] = [new_ste_name, ]
				#	ports_in[element.attrib['element']] = [child.attrib['id'], ]

		# If a port-out

		#	Does the dictionary value also include the macro id?
		#
		elif child.tag == 'port-out':

			for element in child:

				new_ste_name = new_id+delimiter+element.attrib['element']
				to_port = new_id+delimiter+child.attrib['id']

				if new_ste_name in ports_out:
				#if child.attrib['id'] in ports_out:
					ports_out[new_ste_name].append(to_port)
				#	ports_out[child.attrib['id']].append(element.attrib['element'])
				else:
					ports_out[new_ste_name] = [to_port, ]
				#	ports_out[child.attrib['id']] = [element.attrib['element'], ]

	return ports_in, ports_out


def replace_substitutions(body, substitutions):

	for child in body:

		if 'symbol-set' in child.attrib:

			if child.attrib['symbol-set'] in substitutions:

				if VERBOSITY:
					print "Replacing ", child.attrib['symbol-set'], " with ", substitutions[child.attrib['symbol-set']]

				child.set('symbol-set', substitutions[child.attrib['symbol-set']])
		
		if VERBOSITY:
			print child.tag, "...", child.attrib
	return 0

def grab_macro_details(macro):

	activations = {}
	substitutions = {}

	macro_id = macro.attrib['id']
	macro_use = macro.attrib['use']

	# Replace macro_use with actual address
	if macro_use in reference_addresses:
		macro_use = reference_addresses[macro_use]
	else:
		print "Couldnt replace ", macro_use

	# Not necessarily used
	activate_out = macro.find('activate-out')
	subs = macro.find('substitutions')			

	# Grab outward activations
	if activate_out is not None:
		activations = grab_activations(activate_out)

	# Grab substitutions
	if subs is not None:
		substitutions = grab_substitutions(subs)

	if VERBOSITY:
		print "Macro id: ", macro_id, " Macro use: ", macro_use
		print "Activations: ", activations
		print "Substitutions: ", substitutions
		print "-------------"


	return macro_id, macro_use, activations, substitutions

# Print children
def print_children(root):
	for child in root:
		print child.tag, child.attrib
	return

# Load a library of macro definitions
def load_library(library):

	library_dictionary = {}
	
	library_filename = library.attrib['ref'].strip()

	if not os.path.isfile(library_filename):
		print "Error: %s cannot be found as a valid library file" % library_filename
		exit()

	else:

		print "Loading Dictionary of Macro Definitions"
		library_tree = ET.parse(library_filename)
		root = library_tree.getroot()

		library_defs = root.findall('library-definition')

		for library_def in library_defs:

			library_id = library_def.attrib['id']

			for include_macro in library_def.findall('include-macro'):

				macro_ref = include_macro.attrib['ref']
				key = library_id+'.'+macro_ref.split('.')[0]
				library_dictionary[key] = macro_ref
				print key +" -> ", macro_ref

		return library_dictionary



# Main()
if __name__ == "__main__":

	# Verify argument count
	if len(sys.argv) != 3 or ['-h', '--help'] in sys.argv :
		print "Usage: flattener.py <input anml> <flattened output>"
		exit()

	else:

		# Grab input and output file names
		input_filename = sys.argv[1]
		output_filename = sys.argv[2]

		# Parse the root XML file
		try:
			if VERBOSITY:
				print "Parsing: ", input_filename
				
			tree = ET.parse(input_filename)

		except IOError:
			print "Failed to open Input Filename: ", input_filename
			exit()

		# Grab the root node
		root = tree.getroot()

		# If include-macro is defined at root level (we're assuming there's only one)
		include_macros = root.findall('include-macro')

		print include_macros

		if len(include_macros) > 0 :

			for include_macro in include_macros:

				macro_filename =  include_macro.attrib['ref']

				if not os.path.isfile(macro_filename):
					print "ERROR: %s cannot be found as a valid macro " % macro_filename
					exit()
				else:
					reference_key = (macro_filename[0:macro_filename.find('_macro.anml')]).strip()
					reference_addresses[reference_key] = macro_filename
					#print "reference addresses[", reference_key, '] = ', macro_filename
				root.remove(include_macro)

		# If include-library is defined at the root level
		include_library = root.find('include-library')

		print include_library

		if include_library is not None:

			reference_addresses = load_library(include_library)
			root.remove(include_library)


		# Check if in automata level of anml
		automata_network = root.find('automata-network')

		if automata_network is not None:
			root = automata_network

		parent_id = 'root'

		# Empty dictionary to populate with new names and connection
		connection_dictionary = {}

		# Iterate through each macro
		for macro in root.findall('macro-reference'):

			# Flatten the macro (root is root and the current subtree we're into)
			root, connection_dictionary = flatten(root, root, macro, parent_id, connection_dictionary)
			
			# We're done with the macro; remove it
			root.remove(macro)

		# Activation tags for different elements
		activation_dictionary = {'state-transition-element':'activate-on-match',
					'counter':'activate-on-target',
					'inverter':'activate-on-high'}

		# print all children of root
		for child in root:

			# If any root elements have not been translated; translate (:, delimiter)
			if 'id' in child.attrib:
				if 'root' not in child.attrib['id']:
					child.set('id', 'root' + delimiter + child.attrib['id'])

			if child.tag in activation_dictionary:
				activation_string = activation_dictionary[child.tag]

			else:
				continue

			for link in child.findall(activation_string):#'activate-on-match'):

				if 'root' not in link.attrib['element']:
					old_value = "root" + delimiter + link.attrib['element']

				else:
					old_value = link.attrib['element']

				# If the old element value used ':', substitute for '_'; but not for counter
				if child.tag != 'counter':
					old_value = old_value.replace(':', delimiter)

				if old_value in connection_dictionary:

					# Make a shallow copy for this link; may need it several times
					dests = copy.deepcopy(connection_dictionary[old_value])

					if dests:

						link.set('element', dests.pop(0))

						while len(dests) > 0:

							temp_link = copy.deepcopy(link)
							temp_link.set('element', dests.pop(0))
							child.append(temp_link)
					else:
						link.set('element', old_value)
				else:
					if VERBOSITY:
						print old_value, " not in the dictionary"

					link.set('element', old_value)

		tree.write(output_filename)
